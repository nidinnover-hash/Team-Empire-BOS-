import re
from pathlib import Path


def test_templates_have_no_inline_style_or_script_blocks() -> None:
    templates_dir = Path("app/templates")
    inline_style = re.compile(r"<style\b", re.IGNORECASE)
    inline_script = re.compile(r"<script(?![^>]*\bsrc=)", re.IGNORECASE)
    offenders: list[str] = []

    for html_file in templates_dir.glob("*.html"):
        text = html_file.read_text(encoding="utf-8")
        if inline_style.search(text):
            offenders.append(f"{html_file}: inline <style> found")
        if inline_script.search(text):
            offenders.append(f"{html_file}: inline <script> found")

    assert not offenders, "Template asset contract violated:\n" + "\n".join(offenders)


def test_templates_do_not_use_legacy_branding_terms() -> None:
    templates_dir = Path("app/templates")
    legacy_terms = [
        "AI Command Center",
        "Talk Mode",
    ]
    offenders: list[str] = []

    for html_file in templates_dir.glob("*.html"):
        text = html_file.read_text(encoding="utf-8")
        for term in legacy_terms:
            if term in text:
                offenders.append(f"{html_file}: contains legacy term '{term}'")

    assert not offenders, "Branding contract violated:\n" + "\n".join(offenders)
