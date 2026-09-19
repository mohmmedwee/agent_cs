"""QW3: case-insensitive search without offset drift."""

from __future__ import annotations

from agent_console.services.tools.search_files import find_ci


def test_metacharacters_match_literally() -> None:
    haystack = "call foo(bar) then use a.* pattern"
    assert find_ci(haystack, "foo(bar)") == (5, 13)
    assert find_ci(haystack, "a.*") == (23, 26)
    assert find_ci(haystack, "missing*") is None


def test_offsets_correct_when_capital_i_with_dot_appears_earlier() -> None:
    """Turkish İ (U+0130) case-folds to length > 1 under str.lower(); offsets must not drift."""
    # "İ" alone lowercases to "i" + combining dot (2 chars) on many Python builds.
    prefix = "İ"
    needle = "TARGET"
    haystack = f"{prefix} before {needle} after"
    span = find_ci(haystack, "target")
    assert span is not None
    start, end = span
    assert haystack[start:end] == needle
    assert start == haystack.index(needle)
    assert end == start + len(needle)
