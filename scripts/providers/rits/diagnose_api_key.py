#!/usr/bin/env python3
"""Data-focused diagnostic: navigate RITS, collect page state for both
services (inference + restricted-glm), and test the API key retrieval
code paths. No screenshots, no HTML dumps — just structured text output."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from fetch_api_key import (
    _find_copy_button,
    _find_show_button,
    _is_restricted_glm_endpoint,
    find_endpoint_in_service,
    read_api_key,
)
from scrape_rits_models import (
    _find_endpoint_elements,
    dismiss_terms_modal,
    get_available_services,
    scrape_endpoints,
    select_service,
    wait_for_rits_ready,
)

URL = "https://rits.fmaas.res.ibm.com/"
_SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = _SCRIPT_DIR / "playwright-profile"
GLM_ENDPOINT = "/zai-org-glm-5-1-fp8"


def heading_texts(page) -> list[str]:
    """Collect all heading-level text from the page."""
    return page.evaluate("""
        () => Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]'))
            .map(el => el.textContent?.trim() ?? '')
            .filter(Boolean)
    """)


def api_key_field_state(page) -> dict:
    """Read the API key input field state."""
    try:
        field = page.locator("#userkey-passwordinput")
        visible = field.is_visible(timeout=3_000)
        value = field.input_value(timeout=3_000) if visible else ""
        return {
            "visible": visible,
            "value_preview": f"{value[:8]}..." if len(value) > 8 else value,
            "value_length": len(value),
            "masked": "*" in value,
        }
    except Exception as e:
        return {"error": str(e)}


def button_inventory(page) -> list[dict]:
    """List all buttons in the API key table with their attributes."""
    try:
        table = page.locator('table:has(#userkey-passwordinput)')
        btns = table.locator("button")
        count = btns.count()
        result = []
        for i in range(min(count, 10)):
            btn = btns.nth(i)
            cls = btn.get_attribute("class") or ""
            aria = btn.get_attribute("aria-label") or ""
            title = btn.get_attribute("title") or ""
            labelledby = btn.get_attribute("aria-labelledby") or ""
            text = (btn.text_content() or "").strip()[:60]
            visible = btn.is_visible()
            result.append({
                "index": i,
                "class": cls.split()[0] if cls else "",
                "aria-label": aria,
                "title": title,
                "aria-labelledby": labelledby,
                "text": text,
                "visible": visible,
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def endpoint_list(page) -> list[str]:
    """Get endpoint list via the JS scraper."""
    try:
        return _find_endpoint_elements(page)
    except Exception as e:
        return [f"error: {e}"]


def show_button_test(page) -> dict:
    """Test _find_show_button()."""
    try:
        btn = _find_show_button(page)
        if btn is None:
            return {"found": False}
        return {"found": True, "visible": btn.is_visible(), "enabled": btn.is_enabled()}
    except Exception as e:
        return {"found": False, "error": str(e)}


def copy_button_test(page) -> dict:
    """Test _find_copy_button()."""
    try:
        btn = _find_copy_button(page)
        if btn is None:
            return {"found": False}
        return {"found": True, "visible": btn.is_visible(), "enabled": btn.is_enabled()}
    except Exception as e:
        return {"found": False, "error": str(e)}


def diagnose_service(page, service_name: str) -> None:
    """Run all diagnostic checks for the currently selected service."""
    print(f"\n{'='*60}")
    print(f"  Service: {service_name}")
    print(f"{'='*60}")

    print(f"\n  Headings:")
    for h in heading_texts(page):
        print(f"    - {h}")

    print(f"\n  API key field:")
    for k, v in api_key_field_state(page).items():
        print(f"    {k}: {v}")

    print(f"\n  Button inventory:")
    for btn in button_inventory(page):
        parts = [f"idx={btn['index']}"]
        if btn.get("error"):
            parts.append(f"ERROR: {btn['error']}")
        else:
            parts.append(f"class={btn.get('class','')}")
            if btn.get("aria-label"):
                parts.append(f"aria-label={btn['aria-label']}")
            if btn.get("title"):
                parts.append(f"title={btn['title']}")
            if btn.get("aria-labelledby"):
                parts.append(f"aria-labelledby={btn['aria-labelledby']}")
            if btn.get("text"):
                parts.append(f"text={btn['text']}")
            parts.append(f"visible={btn.get('visible')}")
        print(f"    {' | '.join(parts)}")

    print(f"\n  Show button finder: {show_button_test(page)}")
    print(f"  Copy button finder: {copy_button_test(page)}")

    print(f"\n  Endpoints (via JS):")
    eps = endpoint_list(page)
    for ep in eps[:20]:
        print(f"    {ep}")
    if len(eps) > 20:
        print(f"    ... and {len(eps) - 20} more")

    print(f"\n  Endpoints (via scrape_endpoints()):")
    try:
        scraped = scrape_endpoints(page)
        for ep in scraped[:20]:
            print(f"    {ep}")
        if len(scraped) > 20:
            print(f"    ... and {len(scraped) - 20} more")
    except Exception as e:
        print(f"    FAILED: {e}")

    print(f"\n  find_endpoint_in_service({GLM_ENDPOINT}):")
    found = find_endpoint_in_service(page, GLM_ENDPOINT, 30_000)
    print(f"    result: {found}")

    print(f"\n  read_api_key():")
    key = read_api_key(page)
    if key:
        print(f"    SUCCESS: key retrieved (len={len(key)})")
    else:
        print(f"    FAILED: could not read API key")


def main():
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()

            print("1. Navigating to RITS...")
            try:
                page.goto(URL, wait_until="networkidle", timeout=90_000)
            except Exception as e:
                print(f"  Navigation exception: {e}")
                page.wait_for_load_state("domcontentloaded", timeout=90_000)

            wait_for_rits_ready(page)
            dismiss_terms_modal(page, 30_000)

            # Read which service is currently active
            print("\n2. Current service:")
            services = get_available_services(page)
            for svc in services:
                print(f"    - {svc}")
            current_service = services[0] if services else "unknown"
            print(f"  Active: {current_service}")

            # Diagnose the current (likely inference) service
            print("\n3. Diagnosing current service...")
            diagnose_service(page, current_service)

            # Switch to restricted-glm if available
            if "restricted-glm" in services:
                print("\n4. Switching to restricted-glm...")
                try:
                    select_service(page, "restricted-glm", 30_000)
                    diagnose_service(page, "restricted-glm")
                except Exception as e:
                    print(f"  FAILED to switch: {e}")
            else:
                print("\n4. restricted-glm service not available in dropdown")

            # Test the auto-detection logic
            print(f"\n5. Auto-detection tests:")
            print(f"    _is_restricted_glm_endpoint({GLM_ENDPOINT}): {_is_restricted_glm_endpoint(GLM_ENDPOINT)}")
            print(f"    _is_restricted_glm_endpoint(/deepseek-v3-2): {_is_restricted_glm_endpoint('/deepseek-v3-2')}")

            # Test the full fetch_api_key flow for GLM-5.1
            print(f"\n6. Full fetch_api_key flow for {GLM_ENDPOINT}:")
            print(f"    Switching to restricted-glm service...")
            try:
                select_service(page, "restricted-glm", 30_000)
                key = read_api_key(page)
                if key:
                    print(f"    SUCCESS: API key retrieved (len={len(key)})")
                else:
                    print(f"    FAILED: could not read API key")
            except Exception as e:
                print(f"    FAILED: {e}")

            print(f"\n{'='*60}")
            print("  Diagnostic complete.")
            print(f"{'='*60}")

        finally:
            context.close()


if __name__ == "__main__":
    main()
