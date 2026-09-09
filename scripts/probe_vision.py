"""Find out which loaded models can actually see an image.

Sends a generated image with an unguessable answer — a coloured shape whose
colour is chosen at random — so a model that is merely bluffing cannot score by
saying something plausible.
"""

import base64
import io
import struct
import sys
import zlib

import httpx

URL = "http://172.25.44.38:1234/v1/chat/completions"
MODELS = [
    "google/gemma-4-e4b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-35b-a3b",
]

WIDTH = HEIGHT = 160
SHAPE_COLOUR = (0, 128, 255)  # a distinctly blue square on white
COLOUR_NAME = "blue"


def make_png() -> bytes:
    """A white PNG with a solid blue square in the middle, no dependencies."""
    rows = []
    for y in range(HEIGHT):
        row = bytearray([0])  # filter byte: none
        for x in range(WIDTH):
            inside = 40 <= x < 120 and 40 <= y < 120
            row += bytes(SHAPE_COLOUR if inside else (255, 255, 255))
        rows.append(bytes(row))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">2I5B", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def ask(model: str, data_url: str) -> tuple[bool, str]:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "What colour is the square in this image? "
                            "Answer with one word."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 300,
        "temperature": 0,
    }
    try:
        response = httpx.post(URL, json=body, timeout=180)
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {response.text[:160]}"

    message = response.json()["choices"][0]["message"]
    answer = (message.get("content") or "").strip()
    return COLOUR_NAME in answer.lower(), answer.replace("\n", " ")[:120]


def main() -> None:
    png = make_png()
    data_url = f"data:image/png;base64,{base64.b64encode(png).decode()}"
    print(f"image: {len(png)} bytes, a {COLOUR_NAME} square on white\n")

    for model in MODELS:
        correct, detail = ask(model, data_url)
        verdict = "SEES IT" if correct else "no"
        print(f"{model:26s} {verdict:8s} {detail}")


if __name__ == "__main__":
    sys.exit(main())
