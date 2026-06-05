#!/usr/bin/env python3

"""Fetch the API key for a single RITS model endpoint.

Uses the same Playwright persistent profile as scrape_rits_models.py
so the IBM SSO session is reused.  Prints the API key to stdout.

The API key is per-service (not per-endpoint).  This script selects
the service that matches the requested endpoint, then reads the key.
Some endpoints (e.g. restricted-glm models like GLM-5.1) don't appear
in the JS-scraped endpoint list, so the script falls back to matching
known restricted-glm endpoint patterns.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scrape_rits_models import (
    dismiss_terms_modal,
    get_available_services,
    scrape_endpoints,
    select_service,
    wait_for_rits_ready,
)

DEFAULT_URL = "https://rits.fmaas.res.ibm.com/"
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE_DIR = _SCRIPT_DIR / "playwright-profile"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the API key for a single RITS model endpoint.",
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="Endpoint name, e.g. deepseek-v3-2 (with or without leading /).",
    )
    parser.add_argument(
        "--service",
        help="Service name: 'inference' or 'restricted-glm'. "
        "If omitted, tries the service that contains the endpoint.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Persistent browser profile directory.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    return parser.parse_args()


def normalize_endpoint(raw: str) -> str:
    ep = raw.strip()
    if not ep.startswith("/"):
        ep = f"/{ep}"
    return ep


# Known restricted-glm endpoint prefixes.  These endpoints don't appear
# in the JS-scraped endpoint list but use the restricted-glm service key.
RESTRICTED_GLM_PREFIXES = ("/zai-org-",)


def _is_restricted_glm_endpoint(endpoint: str) -> bool:
    slug = endpoint.lstrip("/")
    return any(slug.startswith(p.lstrip("/")) for p in RESTRICTED_GLM_PREFIXES)


def _find_show_button(page):
    """Find the Show/reveal button for the API key field."""
    table = page.locator('table:has(#userkey-passwordinput)')
    # Try by aria-label or title containing "Show" first (most reliable)
    for selector in [
        'button[aria-label*="Show" i]',
        'button[aria-label*="Reveal" i]',
        'button[title*="Show" i]',
    ]:
        btn = table.locator(selector).first
        if btn.count() > 0 and btn.is_visible():
            return btn
    # Fallback: the 2nd borderless-button (Copy=0, Show=1, Regenerate=2)
    btns = table.locator("button.borderless-button")
    if btns.count() > 1:
        return btns.nth(1)
    return None


def _find_copy_button(page):
    """Find the Copy button for the API key field."""
    table = page.locator('table:has(#userkey-passwordinput)')
    # Try by aria-label or title containing "Copy" first
    for selector in [
        'button[aria-label*="Copy" i]',
        'button[title*="Copy" i]',
    ]:
        btn = table.locator(selector).first
        if btn.count() > 0 and btn.is_visible():
            return btn
    # Fallback: the 1st borderless-button (Copy=0)
    btns = table.locator("button.borderless-button")
    if btns.count() > 0:
        return btns.nth(0)
    return None


def read_api_key(page, timeout_ms: int = 10_000) -> str | None:
    """Read the API key from the input field. Clicks Show if masked."""
    input_field = page.locator("#userkey-passwordinput")
    input_field.wait_for(state="visible", timeout=timeout_ms)
    value = input_field.input_value(timeout=5_000)

    # If masked (asterisks), click the Show button to reveal it
    if "*" in value:
        show_btn = _find_show_button(page)
        if show_btn:
            show_btn.click(timeout=5_000)
            page.wait_for_timeout(1_000)
            value = input_field.input_value(timeout=5_000)

    if value and "*" not in value:
        return value

    # Fallback: try clicking Copy and reading from the page
    try:
        copy_btn = _find_copy_button(page)
        if copy_btn:
            copy_btn.click(timeout=3_000)
            page.wait_for_timeout(500)
            cdp = page.context.new_cdp_session(page)
            result = cdp.send("Runtime.evaluate", {
                "expression": "navigator.clipboard.readText()",
                "awaitPromise": True,
            })
            clipboard_text = result.get("result", {}).get("value", "").strip()
            cdp.detach()
            if clipboard_text and "*" not in clipboard_text:
                return clipboard_text
    except Exception:
        pass

    return None


def find_endpoint_in_service(page, endpoint: str, timeout_ms: int) -> bool:
    """Check if the endpoint exists in the currently selected service."""
    try:
        endpoints = scrape_endpoints(page)
        return endpoint in endpoints or endpoint.lstrip("/") in [e.lstrip("/") for e in endpoints]
    except Exception as e:
        print(f"  find_endpoint_in_service({endpoint}): {e}", file=sys.stderr)
        return False


def main() -> int:
    options = parse_args()
    endpoint = normalize_endpoint(options.endpoint)

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        print(
            "Missing dependency: playwright\n"
            "Install with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(options.profile_dir),
            headless=options.headless,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto(options.url, wait_until="networkidle", timeout=90_000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=90_000)

            # Wait for the RITS dashboard (handles IBM SSO login if needed).
            # The user must complete login in the browser within 5 minutes.
            wait_for_rits_ready(page, timeout_ms=300_000)

            # Dismiss the Terms of Use modal if it appears
            dismiss_terms_modal(page, options.timeout_ms)

            # Determine which service to use.
            # The API key is per-service (not per-endpoint), so once we're on
            # the right service we can read the key directly without needing to
            # find or click the endpoint in the list.  Some endpoints (e.g.
            # restricted-glm models) don't appear in the JS-scraped endpoint
            # list at all, so endpoint verification would falsely reject them.
            if options.service:
                select_service(page, options.service, options.timeout_ms)
            else:
                # Try to find the endpoint in the current service first
                if find_endpoint_in_service(page, endpoint, options.timeout_ms):
                    pass  # already on the right service
                else:
                    # Try switching services.  Also try restricted-glm as a
                    # fallback even if the endpoint isn't found in its list,
                    # since restricted-glm endpoints may not appear in the
                    # scraped list but the key is per-service.
                    services = get_available_services(page)
                    found = False
                    for svc in services:
                        select_service(page, svc, options.timeout_ms)
                        if find_endpoint_in_service(page, endpoint, options.timeout_ms):
                            found = True
                            break
                    if not found:
                        # Last resort: if the endpoint URL contains
                        # "restricted-glm" or the endpoint name matches known
                        # restricted-glm models, select that service.
                        if ("restricted-glm" in (options.url or "")) or _is_restricted_glm_endpoint(endpoint):
                            try:
                                select_service(page, "restricted-glm", options.timeout_ms)
                                found = True
                            except Exception as e:
                                print(f"  Could not select restricted-glm: {e}", file=sys.stderr)
                    if not found:
                        print(
                            f"Endpoint {endpoint} not found in any service.",
                            file=sys.stderr,
                        )
                        return 1

            # Try to click the endpoint in the list so the right tab is shown.
            # The API key is per-service so this doesn't affect the key value,
            # but it ensures the page displays the correct endpoint.
            try:
                slug = endpoint.lstrip("/")
                page.locator("button, li").filter(has_text=slug).first.click(timeout=5_000)
                page.wait_for_timeout(500)
            except Exception:
                pass  # endpoint not clickable in list — key is still valid

            # Read the API key — it's per-service, shown at the top of the page
            api_key = read_api_key(page, options.timeout_ms)

            if api_key:
                print(api_key)
                sys.stdout.flush()
                # Write to temp file as a backup for the shell script
                try:
                    with open("/tmp/rits_api_key.txt", "w") as f:
                        f.write(api_key)
                except Exception:
                    pass
                # Use os._exit() to skip Playwright cleanup which hangs on
                # persistent contexts. The key is already on stdout and disk.
                os._exit(0)

            print(
                f"Could not read API key. It may be masked and the Show button failed.",
                file=sys.stderr,
            )
            return 1
        finally:
            try:
                context.close()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
