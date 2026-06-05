"""Tiny sample file fed into the code-review demo by default."""


def add(a, b):
    return a + b


def divide(a, b):
    # Intentionally missing zero-check so the strict reviewer has something to flag.
    return a / b


def parse_number(raw):
    try:
        return float(raw)
    except:  # noqa: E722 — intentional bare except for the reviewer to find
        return None
