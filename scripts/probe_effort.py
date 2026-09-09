"""Find out what actually controls this model's thinking budget.

Runs each candidate control against a prompt heavy enough to provoke long
reasoning, twice, so run-to-run variance does not get mistaken for an effect.
"""

import statistics
import sys
import time

import httpx

URL = "http://172.25.44.38:1234/v1/chat/completions"
MODEL = "qwen/qwen3.8-27b"
HARD = (
    "A team runs a Postgres database that has become slow under load. "
    "Walk through how you would diagnose it, what you would measure, and "
    "which fixes you would consider in what order, and justify the ordering."
)

CASES: list[tuple[str, dict, str]] = [
    ("baseline", {}, HARD),
    ("reasoning_effort=minimal", {"reasoning_effort": "minimal"}, HARD),
    ("reasoning_effort=low", {"reasoning_effort": "low"}, HARD),
    ("reasoning_effort=high", {"reasoning_effort": "high"}, HARD),
    ("enable_thinking=False", {"chat_template_kwargs": {"enable_thinking": False}}, HARD),
    ("/no_think suffix", {}, HARD + " /no_think"),
]
RUNS = 2


def once(extra: dict, text: str) -> tuple[float, int, int]:
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": text}],
        "max_tokens": 1500,
        "temperature": 0.7,
        **extra,
    }
    start = time.monotonic()
    response = httpx.post(URL, json=body, timeout=600)
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    return (
        time.monotonic() - start,
        len(message.get("reasoning_content") or ""),
        len(message.get("content") or ""),
    )


def main() -> None:
    print(f"{'control':28s} {'secs':>7} {'reasoning':>11} {'answer':>8}")
    print("-" * 58)
    results: dict[str, list[int]] = {}

    for label, extra, text in CASES:
        secs, thinks, answers = [], [], []
        for _ in range(RUNS):
            try:
                s, t, a = once(extra, text)
            except httpx.HTTPStatusError as exc:
                print(f"{label:28s}   HTTP {exc.response.status_code}: {exc.response.text[:70]}")
                break
            except Exception as exc:  # noqa: BLE001 - diagnostic script
                print(f"{label:28s}   {type(exc).__name__}: {exc}")
                break
            secs.append(s)
            thinks.append(t)
            answers.append(a)
        if not thinks:
            continue
        results[label] = thinks
        print(
            f"{label:28s} {statistics.mean(secs):7.1f} "
            f"{statistics.mean(thinks):11,.0f} {statistics.mean(answers):8,.0f}"
            f"   runs={thinks}"
        )

    base = results.get("baseline")
    if not base:
        return
    baseline = statistics.mean(base)
    print("\nchange in reasoning length vs baseline:")
    for label, values in results.items():
        if label == "baseline":
            continue
        mean = statistics.mean(values)
        pct = (mean - baseline) / baseline * 100 if baseline else 0
        verdict = "REDUCES thinking" if pct < -25 else "no clear effect"
        print(f"  {label:28s} {pct:+7.0f}%   {verdict}")


if __name__ == "__main__":
    sys.exit(main())
