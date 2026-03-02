import re
from pathlib import Path

CRITICAL_FRONTEND_FILES = [
    Path("app/static/js/coaching-page.js"),
    Path("app/static/js/contacts-page.js"),
    Path("app/static/js/finance-page.js"),
    Path("app/static/js/goals-page.js"),
    Path("app/static/js/projects-page.js"),
]


def test_critical_pages_define_escape_helper_when_using_innerhtml() -> None:
    offenders: list[str] = []
    for path in CRITICAL_FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        if "innerHTML" in text and "var esc = function" not in text:
            offenders.append(f"{path}: innerHTML used without esc helper")
    assert not offenders, "XSS contract failed:\n" + "\n".join(offenders)


def test_critical_pages_do_not_directly_concatenate_raw_item_values() -> None:
    offenders: list[str] = []
    raw_concat = re.compile(r"\+\s*item\.")
    for path in CRITICAL_FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        if raw_concat.search(text):
            offenders.append(f"{path}: direct item.* concatenation found")
    assert not offenders, "XSS contract failed:\n" + "\n".join(offenders)
