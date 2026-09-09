"""Detect degenerate model output (e.g. endless هههههه)."""

from __future__ import annotations

__all__ = ["is_runaway_repetition", "trim_runaway_tail"]

# Same character pasted this many times in a row → stop.
_CHAR_RUN = 64
# A short unit (1–8 chars) repeating this many times at the end → stop.
_UNIT_REPEATS = 24


def is_runaway_repetition(text: str) -> bool:
    if len(text) < _CHAR_RUN:
        return False

    run = 1
    for index in range(1, len(text)):
        if text[index] == text[index - 1]:
            run += 1
            if run >= _CHAR_RUN:
                return True
        else:
            run = 1

    tail = text[-240:]
    for size in range(1, 9):
        unit = tail[-size:]
        if not unit or unit.isspace():
            continue
        repeats = 0
        cursor = len(tail)
        while cursor >= size and tail[cursor - size : cursor] == unit:
            repeats += 1
            cursor -= size
        if repeats >= _UNIT_REPEATS:
            return True
    return False


def trim_runaway_tail(text: str, *, keep_repeats: int = 8) -> str:
    """Clip an endless laugh/spam tail down to a short natural burst."""
    if not text:
        return text

    # Collapse a long same-char run at the end.
    last = text[-1]
    run = 0
    index = len(text)
    while index > 0 and text[index - 1] == last:
        run += 1
        index -= 1
    if run >= _CHAR_RUN:
        return text[:index] + (last * min(keep_repeats, run))

    tail = text[-240:]
    for size in range(1, 9):
        unit = tail[-size:]
        if not unit or unit.isspace():
            continue
        repeats = 0
        cursor = len(tail)
        while cursor >= size and tail[cursor - size : cursor] == unit:
            repeats += 1
            cursor -= size
        if repeats >= _UNIT_REPEATS:
            head = text[: len(text) - len(tail) + cursor]
            return head + unit * min(keep_repeats, repeats)

    return text
