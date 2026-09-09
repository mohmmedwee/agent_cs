# Agent console

A working agent loop over your own OpenAI-compatible endpoint, with a UI that shows the loop.

Endpoint defaults to `http://172.25.44.38:1234/v1` (port 1234 = LM Studio's default; override with
`UPSTREAM` if that's wrong). The `/v1` suffix is required — without it every request 404s.

```bash
pip install -e .

python scripts/check_endpoint.py   # do this first
fastapi dev                        # -> http://localhost:8000
```

`fastapi dev` picks up the entrypoint from `pyproject.toml`. `fastapi run` serves it without reload,
and `python -m agent_console.main` runs it under plain uvicorn.

## Do the check first

`scripts/check_endpoint.py` tests three things in order: the endpoint answers, the model emits a real
`tool_calls` array, and it still does so when streaming. If check 2 or 3 fails, nothing above it
can work, and the fix is in your serving config rather than in this code. The script prints the
specific flag to add.

It runs on the same `ToolCallAccumulator` the server uses, so a reassembly bug fails here rather
than only showing up in production.

The usual failures:

| Symptom | Cause |
|---|---|
| Connection refused | Server bound to `127.0.0.1`. In LM Studio: Developer > Serve on Local Network. |
| `'data'` KeyError, or "Unexpected endpoint" | `UPSTREAM` is missing the `/v1` path segment. |
| Model replies in prose instead of calling a tool | No tool parser. vLLM: `--enable-auto-tool-choice --tool-call-parser hermes` (or `llama3_json` / `mistral` / `pythonic`). |
| Arguments aren't valid JSON | Add constrained decoding — vLLM `--guided-decoding-backend xgrammar`. |
| Works unstreamed, no tool calls when streamed | Some servers only parse tool calls at `stream=False`. Run the loop unstreamed and stream only the final turn. |

## Layout

```
src/agent_console/
├── main.py            app factory, lifespan, entrypoint
├── config.py          Settings, read from env once at startup
├── api/               HTTP layer
│   ├── dependencies.py    Annotated/Depends wiring, all reading app.state
│   └── routes/            chat.py (SSE), health.py, files.py, skills.py
├── schemas/           request/response bodies
├── services/          business logic
│   ├── agent.py           the loop
│   └── tools/             registry.py, context.py, one module per tool
├── repositories/      storage
│   ├── files.py           uploaded files on disk
│   └── skills.py          SKILL.md discovery and loading
├── clients/           outbound I/O
│   ├── upstream.py        the OpenAI-compatible endpoint
│   └── streaming.py       SSE parsing + ToolCallAccumulator (no I/O, shared)
└── models/            domain types: events.py, chat.py, files.py, skills.py
skills/<name>/SKILL.md the agent's own skills
web/index.html         the UI, served by app.frontend()
scripts/check_endpoint.py
```

Dependencies point one way: `api → services → repositories/clients → models`. Nothing in
`services` or below imports from `api`.

## Skills

The agent loads `SKILL.md` files and decides for itself when one applies. The format is the same
one Claude Code, Cursor, and other Agent Skills hosts use — YAML frontmatter with `name` and
`description`, then a markdown body — so a directory written for those tools works here unchanged.

Two ship by default: `answering-well` and `planning-with-intention`.

Loading is progressively disclosed. Only the name and description of each skill reach the system
prompt; the body costs nothing until the model calls `read_skill`. That distinction matters more
than it sounds:

```
SKILL_DIRS='["skills"]'                 2 skills   ~135 tokens per request
SKILL_DIRS='["~/.agents/skills"]'      77 skills  ~5,100 tokens per request
```

Pointing at a large shared library spends thousands of tokens of context on every turn, most of it
irrelevant. Use `SKILL_ALLOWLIST` to take a few skills out of a big directory without paying for
all of them:

```bash
SKILL_DIRS='["skills", "/Users/you/.agents/skills"]' \
SKILL_ALLOWLIST='["diagram-design", "research"]' \
fastapi dev
```

`GET /api/skills` lists what actually loaded. A skill with no `description` is skipped, because the
model would have no basis for choosing it.

## File uploads

Attach files in the UI, or `POST /api/files` as multipart. Uploads go to `uploads/` and the agent
reaches them through two tools rather than having their contents injected into the prompt:
`list_uploaded_files` and `read_uploaded_file`. That keeps a large file out of the context window
and makes the access visible in the UI as a tool call.

Only UTF-8 text is readable. Binary files are stored and listed, but report that their contents
can't be read as text. Adding PDF support means adding `pypdf` and one branch in `FileRepository`.

## How it fits together

```
web/index.html  ──POST /api/chat──>  api/routes/chat.py  ──>  services/agent.py
                <──── typed SSE events ────                        │
                                                    clients/upstream.py ──> your model
```

`AgentService.run()` is the whole loop: call the model, and if the reply carries `tool_calls`, run
them, append the results as `role: "tool"` messages, and call again. It stops when a reply has no
tool calls, or after `max_steps`.

Two details that are easy to get wrong and are handled here:

**Streamed tool calls arrive as fragments.** A single call comes in across several chunks — the
name split mid-word, the JSON arguments a few characters at a time — keyed by `index`. You have to
accumulate by index and concatenate. Overwriting instead of appending is the most common bug in
hand-rolled loops, and it only shows up on longer arguments. This lives in exactly one place,
`clients/streaming.py`, so the server and the diagnostic script cannot drift apart.

**The transport carries typed events, not tokens.** `text_delta`, `tool_call`, `tool_result`,
`error`, `done` — defined as Pydantic models in `models/events.py`. That's what lets the UI draw a
tool call as its own inline block while text streams around it. If you stream a flat token string
you can't ever render the loop, only the prose.

`salvage_text_call()` is a fallback for servers with no tool parser: if the model printed the call
as JSON in its text, it gets picked up anyway. Fix the serving config properly — this just keeps you
moving in the meantime.

## Adding a tool

One file per tool in `services/tools/`. Drop in a module exposing `register` and it's picked up
automatically — modules without that function (`registry`, `context`) are treated as
infrastructure and skipped.

```python
# services/tools/weather.py
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry


def register(registry: ToolRegistry, context: ToolContext) -> None:
    @registry.tool(
        name="get_weather",
        description="Current weather for a city.",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    def get_weather(city: str) -> str:
        ...
```

Sync or async both work; sync functions are pushed to a thread so they don't block the loop.
Exceptions are caught and returned to the model as text, which lets it retry with corrected
arguments instead of the request dying.

When a tool needs a collaborator, add a field to `ToolContext` rather than importing it inside the
tool — that keeps tools constructible in tests.

`calculate` walks the AST rather than calling `eval`. Keep that property for anything that touches
model-generated strings.

## Configuration

Every field on `Settings` is overridable by an environment variable of the same name, or by a
`.env` file: `UPSTREAM`, `MODEL`, `MAX_STEPS`, `REQUEST_TIMEOUT`, `CONNECT_TIMEOUT`,
`SYSTEM_PROMPT`, `SKILL_DIRS`, `SKILL_ALLOWLIST`, `UPLOAD_DIR`, `MAX_UPLOAD_BYTES`,
`MAX_FILE_CHARS`.

## RTL

Every rendered block carries `dir="auto"`, and the container never does. Set direction on a wrapper
and code blocks, lists and numbers inside Arabic text all flip. Tool argument and result panes are
pinned `direction: ltr` because they're JSON regardless of the conversation language.

## Known gaps

These are real, and none of them are hidden behind a comment that says "TODO" and nothing else.

**Uploads don't survive a restart.** `FileRepository` keeps its metadata index in memory while the
bytes go to disk, so after a restart the files are still in `uploads/` but invisible to the app,
and they accumulate. The fix is a sidecar JSON per file plus an index rebuild at startup, about
fifteen lines, contained entirely within `FileRepository`.

**Uploads are server-wide.** Every uploaded file is visible to every request from every browser.
That's the same single-user boundary as conversation history below, and it moves at the same time.

**No conversation identity.** State lives in browser memory and is replayed on each request. For
multi-user, move it server-side keyed by conversation id — that's also what you need before prompt
caching, context trimming, or per-conversation file scoping. It belongs in `repositories/`.

**No auth.** Goes in `api/dependencies.py` as a router-level dependency.

**No tests.** The `ToolCallAccumulator` is pure and has no I/O, so it is the obvious first thing to
cover; `check_endpoint.py` currently exercises it only against a live endpoint.
