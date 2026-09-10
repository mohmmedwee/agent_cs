"""Application settings, read from the environment once at startup."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    upstream: str = Field(
        default="http://172.25.44.38:1234/v1",
        description="Base URL of the OpenAI-compatible endpoint, including the /v1 path.",
    )

    # --- vision -----------------------------------------------------------
    # Images reach the model through the `view_image` tool rather than the
    # conversation: the tool asks a multimodal model a question and returns the
    # answer as text. That indirection is worth keeping even though the current
    # chat model can see, because it means vision still works if the chat model
    # is later switched to one that cannot, and an image never enters the
    # transcript that gets replayed on every subsequent step.
    vision_model: str = Field(
        default="qwen/qwen3.8-27b",
        description=(
            "Multimodal model used to answer questions about images. Pointing "
            "this at the chat model keeps one model resident: loading a second "
            "one alongside it exhausts the host's memory."
        ),
    )
    vision_timeout: float = Field(
        default=300.0, gt=0, description="Seconds to wait for a vision answer."
    )
    max_image_bytes: int = Field(
        default=8 * 1024 * 1024,
        gt=0,
        description="Largest image sent to the vision model.",
    )

    # --- infrastructure -------------------------------------------------
    # Postgres and Redis are shared with other projects on this host, so both
    # are namespaced: a dedicated database, and a Redis logical db plus key
    # prefix. Nothing here may ever issue FLUSHDB or FLUSHALL.
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/agent_console",
        description="Async SQLAlchemy URL for the application database.",
    )
    database_echo: bool = Field(default=False, description="Log every SQL statement.")

    redis_url: str = Field(
        default="redis://127.0.0.1:6379/11",
        description="Redis URL. Logical db 11 is unused by the other apps on this host.",
    )
    redis_prefix: str = Field(
        default="agentconsole:", description="Prefix on every key this app writes."
    )
    cache_search_ttl: int = Field(
        default=3600, gt=0, description="Seconds to cache a web_search result."
    )
    cache_fetch_ttl: int = Field(
        default=86_400, gt=0, description="Seconds to cache a fetched page."
    )

    # --- auth ------------------------------------------------------------
    secret_key: str = Field(
        default="dev-only-change-me",
        description="Signs session cookies. Must be set to a real secret in production.",
    )
    session_ttl: int = Field(
        default=60 * 60 * 24 * 14, gt=0, description="Session cookie lifetime in seconds."
    )
    cookie_secure: bool = Field(
        default=False,
        description="Send the session cookie only over HTTPS. Enable behind TLS.",
    )
    first_user_is_admin: bool = Field(
        default=True,
        description="Grant admin to the first account created, so there is a way in.",
    )
    model: str | None = Field(
        default="qwen/qwen3.8-27b",
        description=(
            "Model id to use for chat. Pinned rather than left to 'whatever the "
            "endpoint lists first', so loading another model cannot silently "
            "change which one answers."
        ),
    )
    max_steps: int = Field(default=8, gt=0, description="Tool-call rounds before the loop gives up.")

    context_window: int = Field(
        default=32_768,
        gt=0,
        description=(
            "Approximate model context window in tokens. Used for the chat "
            "usage meter; set to match your loaded model in LM Studio."
        ),
    )
    context_summarize_ratio: float = Field(
        default=0.70,
        gt=0.1,
        le=0.95,
        description=(
            "When estimated prompt tokens exceed this fraction of "
            "context_window, older turns are folded into a rolling summary."
        ),
    )
    context_keep_recent: int = Field(
        default=6,
        gt=0,
        description=(
            "How many newest transcript messages to keep verbatim when "
            "summarizing (user+assistant pairs count as two)."
        ),
    )
    context_summarize_after_messages: int = Field(
        default=24,
        gt=0,
        description=(
            "Fold older turns once the unsummarized transcript exceeds this "
            "many messages, even if estimated tokens are still under the "
            "ratio budget. Stops short chats with many tiny turns from "
            "never compressing."
        ),
    )
    max_completion_tokens: int = Field(
        default=4_096,
        gt=256,
        description=(
            "Hard cap on tokens generated in one model completion. Prevents "
            "runaway loops (e.g. endless laughter characters) from filling "
            "the context window."
        ),
    )
    max_memory_items: int = Field(
        default=50,
        gt=0,
        description="Max durable user-memory notes per account.",
    )
    max_memory_chars: int = Field(
        default=400,
        gt=0,
        description="Max characters for one user-memory note.",
    )

    approval_required_tools: set[str] = Field(
        default_factory=lambda: {"write_file"},
        description=(
            "Tool names that pause for human allow/deny before running. "
            "write_file is the default: it publishes bytes the user can download."
        ),
    )
    approval_timeout: float = Field(
        default=600.0,
        gt=0,
        description="Seconds to wait for an approval before treating it as deny.",
    )

    request_timeout: float = Field(
        default=1_800.0,
        gt=0,
        description=(
            "Seconds allowed for one model stream. A multi-page write_file "
            "spends this generating arguments with no intermediate reply — "
            "300s was cutting those runs off mid-document."
        ),
    )
    connect_timeout: float = Field(default=10.0, gt=0)
    model_listing_timeout: float = Field(default=15.0, gt=0)

    max_skill_chars: int = Field(
        default=12_000,
        gt=0,
        description="Characters of a skill body read_skill returns before truncating.",
    )

    # Order matters: later directories win a name clash, so the project's own
    # skills come last and override anything with the same name in a shared
    # library.
    skill_dirs: list[Path] = Field(
        default_factory=lambda: [
            Path.home() / ".agents" / "skills",
            Path.home() / ".cursor" / "skills",
            Path("skills"),
        ],
        description="Directories scanned for <name>/SKILL.md. Later entries win on name clashes.",
    )
    skill_allowlist: set[str] = Field(
        # Every loaded skill costs its description on every request, and the
        # shared libraries are full of skills that assume a repo and an editor
        # this server does not have. So the default is a curated set rather than
        # everything found on disk. Clear it to load all of them.
        # Software-engineering skills are deliberately excluded. This is a
        # general assistant, and skills that assume a repository, an issue
        # tracker, or an editor cost context on every request while never
        # matching what is actually asked.
        default_factory=lambda: {
            # This project's own skills.
            "answering-well",
            "planning-with-intention",
            "research",
            "working-with-documents",
            "writing-deliverables",
            "replying-bilingually",
            "diagnosing-problems",
            # Thinking and explaining.
            "grilling",
            "teach",
            "to-questionnaire",
            # Writing.
            "writing-guidelines",
            "writing-shape",
            "writing-fragments",
            "writing-beats",
        },
        description=(
            "If non-empty, only these skill names are loaded. Use it to pull a few "
            "skills out of a large shared library without paying for all of them."
        ),
    )

    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Where uploaded files are written. Created at startup if missing.",
    )
    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024, gt=0, description="Rejected above this size."
    )
    max_file_chars: int = Field(
        default=40_000,
        gt=0,
        description="Characters of a file the read tool returns before truncating.",
    )

    search_results: int = Field(
        default=8, gt=0, le=10, description="Default result count for web_search."
    )
    fetch_timeout: float = Field(default=30.0, gt=0, description="Per-page fetch timeout.")
    max_page_chars: int = Field(
        default=8_000,
        gt=0,
        description=(
            "Characters of a fetched page returned before truncating. Kept small "
            "deliberately: every fetched page is re-sent on each later step, so a "
            "generous limit compounds into slow prefill on a local model."
        ),
    )

    # Stated positively and specifically, because a model with no description
    # of its own capabilities falls back on its training prior — that it is an
    # offline chatbot — and apologises instead of using the tools it has.
    system_prompt: str = (
        "You are a helpful assistant running with live tool access.\n\n"
        "## Who you are\n"
        "You were built by Mohammed Alostah from the Cleverso team. "
        "When someone asks who made you, who built you, or who is behind "
        "cleverso-ai, say that clearly and warmly — and that you are always "
        "happy to help. Do not volunteer this on every reply; only when asked "
        "or when it naturally fits an introduction.\n\n"
        "## What you can actually do\n"
        "You have working, real-time access to the internet through `web_search` "
        "and `fetch_url`. You can read and write files, and do exact arithmetic. "
        "You can also see images: call `view_image` with a specific question and "
        "you get back an answer about what the picture contains. These tools work "
        "right now.\n\n"
        "You can remember durable facts about this user across chats with "
        "`remember`, remove them with `forget`, and inspect them with "
        "`list_memories`. When they say \"remember that…\" or share a stable "
        "preference, store it. When they correct you, update memory. Notes "
        "already stored appear under \"About this user\" in your system "
        "context — use them; do not invent extras.\n\n"
        "Never say you cannot look at an image. You can — ask `view_image`. It "
        "returns words, not pixels, so ask for exactly what you need and ask "
        "again if you need more.\n\n"
        "Never say you cannot access the internet, cannot look things up, have no "
        "live data, or are limited to a training cutoff. That is false here. If "
        "you are tempted to apologise for not knowing something current, search "
        "for it instead — searching first and answering second is always better "
        "than explaining what you cannot do.\n\n"
        "For anything time-sensitive — prices, exchange rates, news, weather, "
        "versions, who currently holds a role — search before answering, even if "
        "you think you know. Your training data is old; the web is not. Report "
        "what you found and when you found it.\n\n"
        "Only if a tool actually fails should you say so, and then say which tool "
        "failed and why.\n\n"
        "## How to answer\n"
        "Call a tool when it gives you a fact you cannot know on your own. Answer "
        "directly when you genuinely already know.\n\n"
        "Sound like a friendly, capable colleague — warm and clear, not stiff or "
        "corporate. Prefer short natural sentences over formal reports. When you "
        "finish a task (for example writing a file), celebrate it briefly and offer "
        "one helpful next step. Do not paste raw /api/files download URLs — the UI "
        "already shows a download card under your message. Avoid cold openers "
        "like \"Done.\" or \"One thing worth flagging:\" — say it the way you would "
        "in chat.\n\n"
        "Reply in the same language the user wrote in, matching their dialect and "
        "register. Keep technical terms in the language they used them in rather "
        "than translating them. Do not mix dialects within one reply.\n\n"
        "## Arabic dialect (critical)\n"
        "When the user writes Arabic dialect, mirror THEIR dialect for the whole "
        "reply — do not drift into another region's Arabic.\n"
        "- Levantine / Jordanian cues (احكيلي، أكتر، بدي، هيك، مش، شو، ليش، "
        "كيفك): stay Levantine. Prefer شو / ليش / بدي / هيك / مش. Never slip "
        "into Gulf وش / تبي / أبي / هالقدر / يبيلّك.\n"
        "- Gulf cues (وش، تبي، أبي، حق، زين): stay Gulf.\n"
        "- Egyptian cues (عامل إيه، عايز، كده): stay Egyptian.\n"
        "- If they write clear Modern Standard Arabic, reply in clear MSA.\n"
        "Write natural native phrasing, not English word order in Arabic letters. "
        "Avoid broken calques like «أكثرك عن نفسي» — say «أحكي لك أكتر عن حالي» "
        "(Levantine) or the matching phrase in their dialect. Use Arabic "
        "punctuation (؟ ،). Keep replies warm and concise unless they ask for "
        "depth.\n\n"
        "Never spam the same character or short laugh forever (no walls of "
        "هههههه or hahaha). A short natural laugh or smile is enough — then "
        "continue the conversation.\n\n"
        "## Creating files\n"
        "When the user asks you to create or export a .xlsx / .docx / .md / .csv "
        "with a described shape (for example \"sales.xlsx with regions and "
        "revenue\"), invent a small plausible sample table and call "
        "`write_file` immediately. Do not dig through uploads or ask them to "
        "paste numbers first unless they clearly said to use a specific file "
        "or \"this data\" that is not in the message. For .xlsx, put a Markdown "
        "pipe table (or CSV) in `content` — that becomes a real workbook."
    )

    @field_validator("upstream")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        # A trailing slash would produce a double slash in every request path.
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
