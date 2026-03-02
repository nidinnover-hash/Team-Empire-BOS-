from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_sdk_release_notes


def test_release_notes_check_passes_with_highlights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    notes = tmp_path / "release-notes.md"
    notes.write_text(
        "\n".join(
            [
                "# SDK Release 0.7.0",
                "",
                "## Highlights",
                "- Added real improvement",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_sdk_release_notes, "NOTES", notes)
    assert check_sdk_release_notes.main() == 0


def test_release_notes_check_fails_for_placeholder_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    notes = tmp_path / "release-notes.md"
    notes.write_text(
        "\n".join(
            [
                "# SDK Release 0.7.0",
                "",
                "## Highlights",
                "- No changelog highlights provided.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_sdk_release_notes, "NOTES", notes)
    with pytest.raises(RuntimeError):
        check_sdk_release_notes.main()
