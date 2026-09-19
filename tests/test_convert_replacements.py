"""QW2: strict convert_upload replacements."""

from __future__ import annotations

from agent_console.services.tools.convert_upload import _apply_replacements


def test_single_match_without_count_succeeds() -> None:
    text, notes = _apply_replacements(
        "Status: Draft — keep going.",
        [{"find": "Status: Draft", "replace": "Status: Final"}],
    )
    assert text == "Status: Final — keep going."
    assert any("replaced 1×" in note for note in notes)


def test_zero_matches_errors() -> None:
    text, notes = _apply_replacements(
        "hello world",
        [{"find": "missing phrase", "replace": "x"}],
    )
    assert text is None
    assert notes and notes[0].startswith("Error:")
    assert "not found" in notes[0]


def test_two_matches_without_count_errors() -> None:
    text, notes = _apply_replacements(
        "aa middle aa",
        [{"find": "aa", "replace": "bb"}],
    )
    assert text is None
    assert notes and notes[0].startswith("Error:")
    assert "2 matches" in notes[0]
    assert "replace_all" in notes[0]


def test_count_one_replaces_only_first_match() -> None:
    text, notes = _apply_replacements(
        "aa middle aa",
        [{"find": "aa", "replace": "bb", "count": 1}],
    )
    assert text == "bb middle aa"
    assert any("replaced 1×" in note for note in notes)
