#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.sync_api import Page


DEFAULT_URL = "https://rits.fmaas.res.ibm.com/"
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "output"
DEFAULT_PROFILE_DIR = _SCRIPT_DIR / "playwright-profile"
SECRET_KEY_RE = re.compile(r"(api.?key|token|secret|password|authorization|credential)", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape non-secret RITS model metadata for the LiteLLM selector."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"RITS URL. Default: {DEFAULT_URL}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for JSON/TSV output. Default: output",
    )
    parser.add_argument(
        "--auth-state",
        type=Path,
        help="Use a Playwright storage state JSON file.",
    )
    parser.add_argument(
        "--save-auth-state",
        type=Path,
        help="Save Playwright storage state after scraping.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Persistent browser profile directory. Default: playwright-profile",
    )
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser.")
    parser.add_argument(
        "--service",
        help="RITS service to scrape (inference, restricted-glm). "
        "If omitted, scrapes all available services.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Scrape only the first N endpoints.")
    parser.add_argument("--delay-ms", type=int, default=250, help="Delay after each click.")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30_000,
        help="Per-model wait timeout.",
    )
    return parser.parse_args()


def is_probably_secret_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if "****************" in value:
        return True
    if re.match(r"(?i)^bearer\s+", value):
        return True
    if re.match(r"^sk-[A-Za-z0-9_-]{12,}", value):
        return True
    if re.match(r"^[A-Fa-f0-9]{32,}$", value):
        return True
    return False


def redact_secrets(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if SECRET_KEY_RE.search(key) or is_probably_secret_value(child)
            else redact_secrets(child)
            for key, child in value.items()
        }
    return "[REDACTED]" if is_probably_secret_value(value) else value


def parse_json_maybe(text: str | None) -> Any:
    if not text or not text.strip():
        return None
    stripped = text.strip()
    try:
        return redact_secrets(json.loads(stripped))
    except json.JSONDecodeError:
        return stripped


def endpoint_slug(endpoint_or_url: str) -> str:
    parsed = urlparse(endpoint_or_url)
    if parsed.scheme and parsed.netloc:
        first_part = parsed.path.strip("/").split("/", 1)[0]
        return f"/{first_part}"
    return endpoint_or_url if endpoint_or_url.startswith("/") else f"/{endpoint_or_url}"


def display_name_for_endpoint(endpoint: str) -> str:
    return endpoint.lstrip("/")


def api_base_for_endpoint(endpoint_url: str) -> str:
    return endpoint_url.rstrip("/") + "/v1"


def hosted_vllm_model_id(served_model_name: str, endpoint: str) -> str:
    return f"hosted_vllm/{served_model_name or display_name_for_endpoint(endpoint)}"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def tsv_escape(value: Any) -> str:
    return str(value or "").replace("\t", " ").replace("\n", " ")


def wait_for_rits_ready(page: "Page", timeout_ms: int = 300_000) -> None:
    """Wait until the RITS dashboard is loaded (user logged in, API key
    field visible).  Handles the multi-step IBM SSO login flow by waiting
    patiently instead of timing out on the login page."""
    print("Waiting for RITS dashboard (complete login in the browser if prompted)...", file=sys.stderr)
    try:
        page.wait_for_selector(
            "#userkey-passwordinput", state="visible", timeout=timeout_ms
        )
    except Exception:
        raise RuntimeError(
            "Timed out waiting for RITS dashboard. "
            "Make sure you completed the IBM SSO login in the browser."
        )


def dismiss_terms_modal(page: "Page", timeout_ms: int = 30_000) -> None:
    """Dismiss the 'Terms of use' modal if it's open."""
    try:
        modal = page.locator(
            '.cds--modal-container[aria-label="Terms of use"]'
        )
        if modal.is_visible(timeout=3_000):
            close_btn = modal.locator("button.cds--btn--primary", has_text="Close")
            close_btn.click(timeout=3_000)
            page.wait_for_timeout(500)
    except Exception:
        pass


def select_service(page: "Page", service: str, timeout_ms: int = 30_000) -> None:
    """Select a service from the dropdown (inference or restricted-glm)."""
    dropdown = page.locator("#service-dropdown")
    dropdown.click(timeout=timeout_ms)
    page.locator("#service-dropdown .cds--list-box__menu-item").first.wait_for(
        state="visible", timeout=5_000
    )
    option = dropdown.locator(
        f".cds--list-box__menu-item:has-text('{service}')"
    ).first
    option.click(timeout=timeout_ms)
    # Wait for the page to refresh: the API key field re-renders and
    # the endpoint list reloads.  3s is conservative but reliable.
    page.wait_for_selector(
        "#userkey-passwordinput", state="visible", timeout=10_000
    )
    page.wait_for_timeout(3_000)


def get_available_services(page: "Page") -> list[str]:
    """Read available service names from the dropdown without changing it."""
    dropdown = page.locator("#service-dropdown")
    current = dropdown.locator(".cds--list-box__label").first.text_content(timeout=5_000) or ""
    services = [current.strip()] if current.strip() else []
    try:
        dropdown.click(timeout=5_000)
        dropdown.locator(".cds--list-box__menu-item").first.wait_for(
            state="visible", timeout=5_000
        )
        items = dropdown.locator(".cds--list-box__menu-item").all_text_contents()
        for item in items:
            name = item.strip()
            if name and name not in services:
                services.append(name)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
    return services


def _find_endpoint_elements(page: "Page") -> list[str]:
    return page.evaluate(
        """
        () => {
          const textValues = Array.from(document.querySelectorAll("button, li, span, div"))
            .map((element) => element.textContent?.trim() ?? "")
            .filter(Boolean);
          return Array.from(new Set(
            textValues
              .filter((text) => /^\\/[a-z0-9][a-z0-9-]+$/i.test(text))
              .map((text) => text.trim())
          )).sort();
        }
        """
    )


def scrape_endpoints(page: "Page", heading_timeout_ms: int = 5_000) -> list[str]:
    # Wait for the endpoint list heading. Different RITS services may use
    # different heading text ("Model Inference Endpoints" vs. something else),
    # so fall back to just waiting for endpoint elements if the heading isn't found.
    try:
        page.wait_for_selector(
            "text=Model Inference Endpoints", timeout=heading_timeout_ms
        )
    except Exception:
        page.wait_for_timeout(2_000)
    # Poll until the endpoint list stabilizes (same result twice in a row).
    # This handles the case where the old service's endpoints are still in
    # the DOM while the new service's list is loading.
    prev: list[str] = []
    for attempt in range(15):
        endpoints = _find_endpoint_elements(page)
        if endpoints and endpoints == prev:
            return endpoints
        prev = endpoints
        page.wait_for_timeout(2_000)
    if prev:
        return prev
    raise RuntimeError(
        "Could not find any model endpoint rows after 30s. "
        "The page may use a different heading or endpoint format."
    )


def click_endpoint(page: "Page", endpoint: str, timeout_ms: int) -> None:
    page.locator("button, li").filter(has_text=endpoint).first.click(timeout=timeout_ms)
    slug = endpoint.lstrip("/")
    # Wait for the endpoint detail to load. Try the known heading text first,
    # then fall back to just checking the endpoint slug appears on the page.
    try:
        page.wait_for_function(
            """
            (selectedEndpoint) =>
              document.body.textContent?.includes("Model inference endpoint:") &&
              document.body.textContent?.includes(selectedEndpoint)
            """,
            arg=slug,
            timeout=min(timeout_ms, 5_000),
        )
    except Exception:
        page.wait_for_function(
            """
            (selectedEndpoint) =>
              document.body.textContent?.includes(selectedEndpoint)
            """,
            arg=slug,
            timeout=timeout_ms,
        )


def extract_rows(page: "Page") -> dict[str, str]:
    return page.evaluate(
        """
        () => {
          const rows = {};
          for (const row of document.querySelectorAll('[role="row"]')) {
            const cells = Array.from(row.querySelectorAll('[role="cell"]')).map((cell) =>
              cell.textContent?.trim().replace(/\\s+/g, " ")
            );
            if (cells.length >= 2 && cells[0]) {
              rows[cells[0].replace(/:$/, "")] = cells[1];
            }
          }
          return rows;
        }
        """
    )


def click_tab_if_present(page: "Page", tab_name: str) -> bool:
    tab = page.get_by_role("tab", name=tab_name).first
    if tab.count() == 0:
        return False
    tab.click()
    return True


def extract_active_snippet(page: "Page") -> Any:
    text = (
        page.locator(
            ".cds--tab-content:not([hidden]) pre code, "
            ".cds--tab-content:not([hidden]) pre"
        )
        .first.text_content(timeout=2_000)
        or ""
    )
    return parse_json_maybe(text)


def extract_runtime_config(page: "Page") -> dict[str, Any]:
    config: dict[str, Any] = {}
    if click_tab_if_present(page, "Environment variables"):
        config["environment"] = extract_active_snippet(page)
    if click_tab_if_present(page, "Checkpoint config.json file"):
        config["checkpoint_config"] = extract_active_snippet(page)
    if click_tab_if_present(page, "Checkpoint tokenizer_config.json file"):
        config["tokenizer_config"] = extract_active_snippet(page)
    return config


def extract_notes(page: "Page") -> str:
    try:
        text = page.locator("article.markdown-body").first.text_content(timeout=2_000) or ""
    except Exception:
        text = ""
    return re.sub(r"\s+", " ", text).strip()


def scrape_model(page: "Page", endpoint: str, options: argparse.Namespace) -> dict[str, Any]:
    click_endpoint(page, endpoint, options.timeout_ms)
    page.wait_for_timeout(options.delay_ms)

    rows = extract_rows(page)
    runtime_config = extract_runtime_config(page)
    endpoint_url = rows.get("Model inference endpoint") or f"{options.url.rstrip('/')}{endpoint}"
    environment = dict_or_empty(runtime_config.get("environment"))
    served_model_name = rows.get("Served model name") or environment.get("SERVED_MODEL_NAME") or ""

    return redact_secrets(
        {
            "endpoint": endpoint_slug(endpoint_url),
            "endpoint_url": endpoint_url,
            "api_base": api_base_for_endpoint(endpoint_url),
            "display_name": display_name_for_endpoint(endpoint),
            "served_model_name": served_model_name,
            "litellm_model_id": hosted_vllm_model_id(served_model_name, endpoint),
            "checkpoint_path": rows.get("Model checkpoint path", ""),
            "runtime_image": rows.get("Model runtime image", ""),
            "runtime_config": runtime_config,
            "notes": extract_notes(page),
        }
    )


def write_outputs(output_dir: Path, models: list[dict[str, Any]]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "rits-models.json"
    tsv_path = output_dir / "rits-models.tsv"
    selector_tsv_path = output_dir / "rits_models_for_selector.tsv"

    json_path.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")

    header = [
        "endpoint",
        "endpoint_url",
        "api_base",
        "display_name",
        "served_model_name",
        "litellm_model_id",
        "checkpoint_path",
        "runtime_image",
        "num_gpus",
        "max_model_len",
        "notes",
    ]
    rows = []
    for model in models:
        runtime_config = dict_or_empty(model.get("runtime_config"))
        environment = dict_or_empty(runtime_config.get("environment"))
        rows.append(
            [
                model.get("endpoint", ""),
                model.get("endpoint_url", ""),
                model.get("api_base", ""),
                model.get("display_name", ""),
                model.get("served_model_name", ""),
                model.get("litellm_model_id", ""),
                model.get("checkpoint_path", ""),
                model.get("runtime_image", ""),
                environment.get("NUM_GPUS", ""),
                environment.get("MAX_MODEL_LEN", ""),
                model.get("notes", ""),
            ]
        )
    tsv_path.write_text(
        "\n".join("\t".join(tsv_escape(value) for value in row) for row in [header, *rows])
        + "\n",
        encoding="utf-8",
    )

    selector_rows = []
    for model in models:
        endpoint_url = model.get("endpoint_url", "")
        parsed = urlparse(endpoint_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        selector_rows.append(
            [
                model.get("endpoint", ""),
                model.get("served_model_name", ""),
                model.get("display_name", ""),
                base_url,
            ]
        )
    selector_tsv_path.write_text(
        "# endpoint\tserved_model_name\tdisplay_name\tbase_url\n"
        + "\n".join("\t".join(tsv_escape(value) for value in row) for row in selector_rows)
        + "\n",
        encoding="utf-8",
    )

    return {
        "json": json_path,
        "tsv": tsv_path,
        "selector_tsv": selector_tsv_path,
    }


def main() -> int:
    options = parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: playwright\n"
            "Install with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        if options.auth_state:
            browser = playwright.chromium.launch(headless=options.headless)
            context = browser.new_context(storage_state=str(options.auth_state))
        else:
            context = playwright.chromium.launch_persistent_context(
                str(options.profile_dir),
                headless=options.headless,
            )
            browser = None

        try:
            page = context.pages[0] if context.pages else context.new_page()
            
            # Try navigation with fallback for auth redirects
            try:
                page.goto(options.url, wait_until="networkidle", timeout=90_000)
            except Exception:
                # If goto fails (ERR_ABORTED from auth redirects), wait for the page to settle
                page.wait_for_load_state("domcontentloaded", timeout=90_000)

            wait_for_rits_ready(page)
            dismiss_terms_modal(page)

            # Determine which services to scrape
            if options.service:
                services_to_scrape = [options.service]
            else:
                services_to_scrape = get_available_services(page)
            print(f"Services to scrape: {', '.join(services_to_scrape)}")

            models: list[dict[str, Any]] = []
            for svc in services_to_scrape:
                print(f"\nSelecting service: {svc}")
                select_service(page, svc)
                dismiss_terms_modal(page)

                endpoints = scrape_endpoints(page)
                selected = endpoints[: options.limit] if options.limit > 0 else endpoints
                print(f"[{svc}] Found {len(endpoints)} endpoints; scraping {len(selected)}.")

                for index, endpoint in enumerate(selected, 1):
                    prefix = f"[{svc} {index}/{len(selected)}]"
                    print(f"{prefix} {endpoint} ... ", end="", flush=True)
                    try:
                        model = scrape_model(page, endpoint, options)
                        model["service"] = svc
                        models.append(model)
                        print(model.get("served_model_name") or "no served model name")
                    except Exception as exc:  # noqa: BLE001
                        print(f"failed: {exc}")
                        models.append(
                            {
                                "endpoint": endpoint,
                                "display_name": display_name_for_endpoint(endpoint),
                                "service": svc,
                                "error": str(exc),
                            }
                        )

            outputs = write_outputs(options.output_dir, models)
            if options.save_auth_state:
                context.storage_state(path=str(options.save_auth_state))
                print(f"Saved auth state: {options.save_auth_state}")
            print(f"Wrote {outputs['json']}")
            print(f"Wrote {outputs['tsv']}")
            print(f"Wrote {outputs['selector_tsv']}")
        finally:
            context.close()
            if browser:
                browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
