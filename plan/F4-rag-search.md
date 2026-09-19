# F4 — Search across uploads (RAG)

**Size:** L (6–8 days) · **Backend:** yes · **Migration:** yes · **New deps:** Postgres `vector` extension,
`pgvector` (py) · **Depends on:** 00-foundation (F3 recommended: citation clicks open the workspace)

## What the user gets
Questions answered from **all** their files at once ("what do my contracts say about termination?", "ما هي
شروط الإلغاء في العقود؟"), with citations like **[1]** in the answer. Hovering a citation shows the passage,
and clicking it opens the file in the workspace. The Files page shows whether each file is indexed.

## Current state
- `search_uploaded_files` (`services/tools/search_files.py`): **substring** match over every readable file,
  with offsets and PDF page numbers. It misses paraphrases, synonyms, and Arabic spelling variants (أ/ا/إ, ة/ه,
  diacritics).
- `extract_text(data, name)` (`repositories/extraction.py:247`) → text for txt/md/csv/json/docx/pdf. PDF text has
  `--- Page N ---` markers.
- Files: `StoredFileRow` (`db/models.py`) with `is_text`, `is_image`. Bytes on disk.
- Upstream: LM Studio (OpenAI-compatible) at `settings.upstream` (includes `/v1`). It serves `POST /embeddings`
  when an embedding model is loaded.

## Prerequisites (confirm before starting)
1. **pgvector** in the Postgres that `DATABASE_URL` points at: `CREATE EXTENSION vector;` must succeed.
   - macOS Homebrew: `brew install pgvector`, then restart Postgres.
   - Docker: use the image `pgvector/pgvector:pg16` (or pg17).
2. **An embedding model loaded in LM Studio.** For Arabic + English, use **`bge-m3`** (1024 dims, no prefixes
   needed, strong multilingual). `multilingual-e5-large` is the alternative (1024 dims, needs `query: ` /
   `passage: ` prefixes, which the config supports). Check it with:
   `curl $UPSTREAM/embeddings -d '{"model":"<id>","input":["مرحبا"]}' -H 'content-type: application/json'`.

## Design
- **Chunks in Postgres.** A `file_chunks` table with a `vector(1024)` column and a `tsvector` column. Deleting a
  file cascades to its chunks. No new service.
- **Indexing by a background poller**, not by hooking every `save()` call site. There are four of them
  (upload route, `write_file`, `run_python` outputs, `convert_upload`), and a task spawned inside the request
  would run before the file row is committed. The poller claims `index_status='pending'` rows with
  `FOR UPDATE SKIP LOCKED`, so it's safe with several workers.
- **Hybrid retrieval.** Vector top-30 plus full-text top-30, merged with **reciprocal-rank fusion** (k=60).
  Vector search finds paraphrases, and keyword search finds exact names, numbers and IDs, which embeddings are
  bad at.
- **Arabic normalization** for the keyword side: before building the `tsvector` (and on the query), strip
  diacritics and tatweel, and unify alef forms (أ إ آ → ا), ى → ي, ة → ه. Postgres has no Arabic stemmer, so we use
  the `simple` config over normalized text. The embedding side gets the **original** text (the model handles it).
- **Chunking:** split by page (PDF markers) and by Markdown heading, then pack paragraphs into ~3,200-character
  chunks (≈800 tokens) with ~480 characters of overlap. Never split inside a word. Each chunk keeps `page` and
  `heading`.

## Files

| File | Change |
|---|---|
| `pyproject.toml` | `pgvector>=0.3` |
| `migrations/versions/e5f6a7b8c9d0_file_chunks.py` | **new** |
| `src/agent_console/db/models.py` | `FileChunk`; `StoredFileRow.index_status`, `indexed_at`, `index_error` |
| `src/agent_console/config.py` | RAG settings |
| `src/agent_console/clients/upstream.py` | `embed()` |
| `src/agent_console/repositories/text_normalize.py` | **new**: Arabic normalization |
| `src/agent_console/repositories/chunking.py` | **new**: `chunk_document()` (pure) |
| `src/agent_console/repositories/chunks.py` | **new**: `ChunkRepository` (store + hybrid search) |
| `src/agent_console/services/indexer.py` | **new**: poller + `index_one()` |
| `src/agent_console/main.py` | start/stop the indexer in `lifespan` |
| `src/agent_console/services/tools/search_documents.py` | **new** tool |
| `src/agent_console/services/tools/search_files.py` | description points to the new tool for questions |
| `src/agent_console/schemas/files.py`, `api/routes/files.py` | `index_status` in list; `POST /{id}/reindex` |
| `scripts/reindex.py` | **new** backfill |
| `frontend/src/lib/citations.ts` (+ test) | **new** |
| `frontend/src/components/chat/DocumentSearchResults.tsx` | **new** |
| `frontend/src/components/chat/Markdown.tsx` | render `[n]` citation chips |
| `frontend/src/components/chat/Blocks.tsx`, `DocumentPreview.tsx`, `lib/activityLabels.ts` | wire the new tool |
| `frontend/src/pages/FilesPage.tsx` | index status + retry |
| `i18n` | keys below |

---

## Step 1: config

```python
# --- retrieval (RAG) -----------------------------------------------------
rag_enabled: bool = Field(default=False, description="Index uploads and expose search_documents.")
embedding_model: str | None = Field(default=None, description="Embedding model id on the upstream, e.g. bge-m3.")
embedding_dim: int = Field(default=1024, description="Must match the model AND the migration's vector size.")
embedding_query_prefix: str = ""      # "query: " for e5 models
embedding_passage_prefix: str = ""    # "passage: " for e5 models
embedding_batch: int = Field(default=16, ge=1, le=128)
rag_chunk_chars: int = 3200
rag_overlap_chars: int = 480
rag_top_k: int = Field(default=6, ge=1, le=20)
rag_poll_seconds: float = 5.0
rag_max_file_chars: int = Field(default=2_000_000, description="Skip indexing beyond this much text.")
```

## Step 2: migration `e5f6a7b8c9d0_file_chunks.py` (down_revision `d4e5f6a7b8c9`)

```python
from pgvector.sqlalchemy import Vector

DIM = 1024  # keep equal to settings.embedding_dim; changing it needs a new migration + reindex

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("files", sa.Column("index_status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("files", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("files", sa.Column("index_error", sa.String(400), nullable=True))
    op.create_index("ix_files_index_status", "files", ["index_status", "uploaded_at"])

    op.create_table(
        "file_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("heading", sa.String(300), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_norm", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column("tsv", postgresql.TSVECTOR,
                  sa.Computed("to_tsvector('simple', text_norm)", persisted=True)),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("file_id", "ordinal", name="uq_file_chunks_file_ordinal"),
    )
    op.create_index("ix_file_chunks_user_file", "file_chunks", ["user_id", "file_id"])
    op.create_index("ix_file_chunks_tsv", "file_chunks", ["tsv"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_file_chunks_embedding ON file_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    # Existing files: images and unreadable files are 'skipped', the rest 'pending'.
    op.execute("UPDATE files SET index_status = CASE WHEN is_text THEN 'pending' ELSE 'skipped' END")

def downgrade() -> None:
    op.drop_table("file_chunks")
    op.drop_index("ix_files_index_status", table_name="files")
    op.drop_column("files", "index_error")
    op.drop_column("files", "indexed_at")
    op.drop_column("files", "index_status")
    # leave the extension installed; other DBs objects may use it
```

`is_text` is computed at save time from `extract_text`, so it's a reliable "can we read this" flag. New files get
`pending` from the server default. `FileRepository.save` should set `index_status = "pending" if is_text else
"skipped"` explicitly, to match.

## Step 3: models

```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed
from sqlalchemy.dialects.postgresql import TSVECTOR

class FileChunk(Base):
    __tablename__ = "file_chunks"
    id: Mapped[UUID] = _pk()
    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column()
    page: Mapped[int | None] = mapped_column(nullable=True)
    heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    text_norm: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(1024), nullable=True)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', text_norm)", persisted=True))
```

`StoredFileRow` gets `index_status`, `indexed_at` and `index_error` to match the migration.

## Step 4: `repositories/text_normalize.py`

```python
import re

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})

def normalize_for_search(text: str) -> str:
    """Spelling-insensitive form for keyword matching (never shown to anyone)."""
    text = _DIACRITICS.sub("", text).replace(_TATWEEL, "")
    return text.translate(_MAP).lower()
```

Tests: `normalize_for_search("إِدَارَة") == "اداره"`, Latin is lowercased, and digits are untouched.

## Step 5: `repositories/chunking.py`

```python
@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page: int | None
    heading: str | None

_PAGE = re.compile(r"^--- Page (\d+) ---$", re.M)
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")

def chunk_document(text: str, *, size: int = 3200, overlap: int = 480) -> list[Chunk]:
```

Algorithm:
1. **Sections.** If `_PAGE` matches, split on it into `(page, body)` pairs. Otherwise one section with
   `page=None`. Inside each section, walk the lines, tracking the latest Markdown heading (`_HEADING`) as the
   current `heading` (keep only the text, max 300 chars).
2. **Paragraphs.** Split the section body on blank lines. A paragraph longer than `size` is split further on
   sentence ends (`(?<=[.!؟?])\s+`), and failing that on the last whitespace before `size`, never mid-word.
3. **Pack.** Append paragraphs to the current chunk while `len + len(p) <= size`. When it's full, emit the
   chunk, then start the next chunk with the **tail** of the previous one (last `overlap` characters, cut forward
   to a whitespace) so context carries over. A new page or heading always starts a new chunk (no overlap across
   pages), so page citations stay exact.
4. Drop chunks with fewer than 40 non-space characters. Number `ordinal` from 0.

Tests: a 3-page PDF-style text → chunks carry pages 1/2/3 and none spans two pages; a long paragraph splits on
a sentence; overlap text appears at the start of chunk n+1; Arabic words are never cut; empty or whitespace-only
input → `[]`; headings are carried.

## Step 6: `UpstreamClient.embed()`

```python
async def embed(self, texts: list[str], *, kind: Literal["query", "passage"]) -> list[list[float]]:
    model = self._settings.embedding_model
    if not model:
        raise UpstreamError("embedding_model is not configured")
    prefix = (self._settings.embedding_query_prefix if kind == "query"
              else self._settings.embedding_passage_prefix)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), self._settings.embedding_batch):
        batch = [prefix + t for t in texts[start:start + self._settings.embedding_batch]]
        response = await self._http.post(
            f"{self._settings.upstream}/embeddings",
            json={"model": model, "input": batch},
            timeout=httpx.Timeout(120, connect=self._settings.connect_timeout),
        )
        if response.status_code >= 400:
            raise UpstreamError(f"embeddings failed ({response.status_code}): {response.text[:300]}")
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors.extend(item["embedding"] for item in data)
    if vectors and len(vectors[0]) != self._settings.embedding_dim:
        raise UpstreamError(
            f"{model} returns {len(vectors[0])}-dim vectors; embedding_dim is {self._settings.embedding_dim}"
        )
    return vectors
```

The dimension check turns a silent "wrong model loaded" into a clear failure on the file.

## Step 7: `repositories/chunks.py`

```python
@dataclass(frozen=True)
class ChunkHit:
    chunk_id: UUID
    file_id: UUID
    file_name: str
    page: int | None
    heading: str | None
    text: str
    score: float

class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def replace_for_file(self, file: StoredFileRow, chunks: list[Chunk],
                               vectors: list[list[float]]) -> None:
        await self._session.execute(delete(FileChunk).where(FileChunk.file_id == file.id))
        self._session.add_all(
            FileChunk(file_id=file.id, user_id=file.user_id, ordinal=c.ordinal, page=c.page,
                      heading=c.heading, text=c.text, text_norm=normalize_for_search(c.text),
                      embedding=v)
            for c, v in zip(chunks, vectors, strict=True)
        )

    async def search(self, user_id: UUID, query: str, query_vec: list[float], *,
                     top_k: int, file_ids: list[UUID] | None = None) -> list[ChunkHit]:
```

`search` runs one SQL statement (via `text()` with bound params). `:fids` is `NULL` when there's no filter:

```sql
WITH q AS (
  SELECT CAST(:qvec AS vector) AS v, plainto_tsquery('simple', :qnorm) AS t
),
vec AS (
  SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> q.v) AS r
  FROM file_chunks c, q
  WHERE c.user_id = :uid AND c.embedding IS NOT NULL
    AND (CAST(:fids AS uuid[]) IS NULL OR c.file_id = ANY(CAST(:fids AS uuid[])))
  ORDER BY c.embedding <=> q.v
  LIMIT 30
),
kw AS (
  SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.t) DESC) AS r
  FROM file_chunks c, q
  WHERE c.user_id = :uid AND c.tsv @@ q.t
    AND (CAST(:fids AS uuid[]) IS NULL OR c.file_id = ANY(CAST(:fids AS uuid[])))
  ORDER BY ts_rank_cd(c.tsv, q.t) DESC
  LIMIT 30
)
SELECT c.id, c.file_id, f.name, c.page, c.heading, c.text,
       COALESCE(1.0 / (60 + vec.r), 0) + COALESCE(1.0 / (60 + kw.r), 0) AS score
FROM file_chunks c
JOIN files f ON f.id = c.file_id
LEFT JOIN vec ON vec.id = c.id
LEFT JOIN kw  ON kw.id  = c.id
WHERE vec.id IS NOT NULL OR kw.id IS NOT NULL
ORDER BY score DESC
LIMIT :k
```

Pass `qvec` as the pgvector text form `"[0.1,0.2,…]"` (`"[" + ",".join(map(str, vec)) + "]"`) and
`qnorm = normalize_for_search(query)`.

After the query, **dedupe neighbors**: drop a hit if a higher-scored hit is the same file with an adjacent ordinal
(overlap makes neighbors near-duplicates). Then cap it at 2 hits per file unless `file_ids` narrowed the search,
so one long document can't take every slot.

Note: the HNSW index is used for the `ORDER BY … LIMIT` in `vec`. With the `user_id` filter, Postgres may scan.
That's fine up to roughly 10⁵ chunks. Beyond that, see "Later" at the end.

## Step 8: `services/indexer.py`

```python
class Indexer:
    """Background loop: claim pending files, extract → chunk → embed → store."""

    def __init__(self, *, session_factory, upstream: UpstreamClient, settings: Settings,
                 upload_dir: Path) -> None: ...

    async def run_forever(self) -> None:
        await self._reset_stale()                 # 'indexing' older than 10 min → 'pending'
        while True:
            try:
                did_work = await self._tick()
            except Exception:                     # never let the loop die
                logger.exception("indexer tick failed")
                did_work = False
            if not did_work:
                await asyncio.sleep(self._settings.rag_poll_seconds)

    async def _tick(self) -> bool:
        async with self._factory() as session:
            row = (await session.execute(
                select(StoredFileRow)
                .where(StoredFileRow.index_status == "pending")
                .order_by(StoredFileRow.uploaded_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )).scalar_one_or_none()
            if row is None:
                return False
            row.index_status = "indexing"
            await session.commit()
            file_id = row.id
        await self.index_one(file_id)
        return True

    async def index_one(self, file_id: UUID) -> None:
        async with self._factory() as session:
            row = await session.get(StoredFileRow, file_id)
            if row is None:
                return
            try:
                files = FileRepository(session, self._upload_dir, self._settings.max_upload_bytes)
                text = await files.text(row.user_id, str(row.id))     # extraction + caching path
                if len(text) > self._settings.rag_max_file_chars:
                    text = text[: self._settings.rag_max_file_chars]
                chunks = await asyncio.to_thread(
                    chunk_document, text,
                    size=self._settings.rag_chunk_chars, overlap=self._settings.rag_overlap_chars)
                vectors = await self._upstream.embed([c.text for c in chunks], kind="passage") if chunks else []
                await ChunkRepository(session).replace_for_file(row, chunks, vectors)
                row.index_status, row.indexed_at, row.index_error = "ready", utcnow(), None
            except UnreadableFileError:
                row.index_status, row.index_error = "skipped", None
            except Exception as exc:  # noqa: BLE001
                logger.exception("indexing %s failed", file_id)
                await session.rollback()
                row = await session.get(StoredFileRow, file_id)
                if row is None:
                    return
                row.index_status, row.index_error = "failed", str(exc)[:400]
            await session.commit()
```

`FileRepository.text()` (`files.py:169`) already raises `UnreadableFileError` for binaries. Check the exact
signature while implementing.

## Step 9: `main.py` lifespan

After `app.state.chat_jobs = ChatJobBroker()`:

```python
indexer_task = None
if settings.rag_enabled:
    app.state.indexer = Indexer(session_factory=app.state.session_factory,
                                upstream=app.state.upstream_client, settings=settings,
                                upload_dir=upload_dir)
    indexer_task = asyncio.create_task(app.state.indexer.run_forever(), name="rag-indexer")
```

In `finally`: `if indexer_task: indexer_task.cancel(); with suppress(asyncio.CancelledError): await indexer_task`.

## Step 10: tool `services/tools/search_documents.py`

The tool needs a DB session for `ChunkRepository`. `ToolContext` has `files: FileRepository`, which holds the
session. Add `chunks: ChunkRepository | None` to `ToolContext`, built in `routes/chat.py` next to `files`, using
the same `session` (and in `api/dependencies.py` wherever a `ToolContext` is built).

```python
def register(registry: ToolRegistry, context: ToolContext) -> None:
    if not context.settings.rag_enabled or context.chunks is None:
        return

    @registry.tool(
        name="search_documents",
        description=(
            "Find passages in the user's uploaded and generated files that answer a question, "
            "by meaning (works across Arabic and English wording). Use it FIRST for any question "
            "about the user's documents. Cite passages in your answer as [1], [2] matching the "
            "numbers returned. If you need more context, call read_uploaded_file on that file. "
            "Use search_uploaded_files instead for an exact string (an ID, a code, a name)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question or topic, in any language."},
                "file_names": {"type": "array", "items": {"type": "string"},
                               "description": "Optional: only search these files."},
            },
            "required": ["query"],
        },
    )
    async def search_documents(query: str, file_names: list[str] | None = None) -> str:
        file_ids = None
        if file_names:
            file_ids = [ (await context.files.get(context.user_id, n)).id for n in file_names ]  # UnknownFileError → message
        vec = (await context.upstream.embed([query], kind="query"))[0]
        hits = await context.chunks.search(context.user_id, query, vec,
                                           top_k=context.settings.rag_top_k, file_ids=file_ids)
        if not hits:
            return "No matching passages. The files may still be indexing, or try other words."
        return "\n\n".join(_format(i, h) for i, h in enumerate(hits, start=1))
```

Output format per hit. It's **machine-parseable** because the frontend reads it:

```
[1] contract-2024.pdf · p. 7 · §Termination · file:3f2c…-uuid
<passage text, max 1,200 chars>
```

(`§heading` only when present, `p. N` only when there's a page.) Handle `UnknownFileError` on `file_names` by
returning `"Error: no file named '<n>'. Call list_files to see names."`.

Also add a note in `search_files.py`'s description: "For questions about content, prefer search_documents when
available."

## Step 11: files API
- `schemas/files.py` `FileResponse`: add `index_status: str = "skipped"`, `index_error: str | None = None`.
- `routes/files.py`: `POST /api/files/{file_id}/reindex` sets `index_status='pending'` and clears the error
  (404 if it isn't the user's file), and returns the file.
- `scripts/reindex.py`: `--user EMAIL`, `--all`, `--only-failed`. It sets matching rows to `pending`, and the
  running indexer picks them up. Use it after changing the embedding model (with `--all`, after truncating
  `file_chunks`).

## Step 12: frontend

**`lib/citations.ts`**

```ts
export type DocHit = { n: number; fileId: string; name: string; page?: number; heading?: string; text: string }

const HEADER = /^\[(\d+)\] (.+?)(?: · p\. (\d+))?(?: · §(.+?))? · file:([0-9a-f-]{36})$/

export function parseDocHits(result: string): DocHit[] { /* split on blank line before "[n] "; match HEADER */ }

/** Citation numbers → hit, for the answer of one assistant turn (latest search_documents wins). */
export function citationMap(blocks: Block[]): Map<number, DocHit> { ... }
```

Tests: the full header, header without page/heading, Arabic file names, and passage text containing `[2]`
(it must not be mistaken for a header, since headers only match at line start after a blank line).

**Answer citations.** `Markdown.tsx` takes an optional `citations?: Map<number, DocHit>`. When present, replace
`[n]` text (not inside code or links) with a `<CitationChip hit>`: a superscript pill `text-[10px] px-1
rounded bg-violet-tint text-violet-ink`. On hover or focus it shows a popover with file name, page and the first
300 characters of the passage. Clicking it calls `openArtifact({ fileId, name })`. If `n` has no hit, leave the
text as it is. `AssistantTurnBlocks` (`ChatPage.tsx`) computes `citationMap(turn.blocks)` and passes it to the
answer `BlockView`s.

**Trail/Steps.** `DocumentSearchResults.tsx`, modeled on `WebSearchResults.tsx`: the header "Searched your files
for "<query>"", then rows of badge (`fileBadgeClass`) + name + `p. N` + a two-line excerpt. A row click opens the file.
`Blocks.tsx`: route `block.name === 'search_documents'` to it. `activityLabels.ts`: the label
`chat.searchedDocs` and `toolDetail` = the query in quotes.

**Sources tab.** `collectConversationSources` in `DocumentPreview.tsx` also collects doc hits, rendered in two
groups, "Web" and "Your files" (only non-empty groups show). The count includes both.

**Files page.** A status column (or a dot after the name): `pending`/`indexing` = spinner + `files.indexing`,
`ready` = nothing (quiet), `failed` = red dot + a `files.indexFailed` tooltip with `index_error`, plus a Retry icon
button → `POST /reindex`, then invalidate the files query. Poll the files query every 5 s while any row is
pending/indexing (`refetchInterval` returning `false` otherwise).

**i18n**

| key | en | ar |
|---|---|---|
| `chat.searchedDocs` | Searched your files | بحث في ملفاتك |
| `chat.searchingDocs` | Searching your files | جارٍ البحث في ملفاتك |
| `chat.citationOpen` | Open source | افتح المصدر |
| `files.indexing` | Indexing… | جارٍ الفهرسة… |
| `files.indexFailed` | Couldn't index this file | تعذّرت فهرسة هذا الملف |
| `files.reindex` | Retry indexing | إعادة الفهرسة |
| `workspace.sourcesWeb` | Web | الويب |
| `workspace.sourcesFiles` | Your files | ملفاتك |

## Tests
- Pure: `normalize_for_search`, `chunk_document` (step 5 list), RRF/dedupe helper (extract it as a pure
  function `fuse(vec_ids, kw_ids, k=60)` and test it), `_format`/`parseDocHits` round trip (Python output parsed
  by the TS parser: keep a shared fixture file `tests/fixtures/doc_hits.txt` that both test suites read).
- `@pytest.mark.db` (needs pgvector in the test DB): insert 2 files with hand-made 1024-d vectors, then
  `search` ranks the right chunk first, a keyword-only match (an ID) is found, and a user filter prevents
  cross-user leaks. Deleting the file removes its chunks.
- Indexer with a fake upstream (returns fixed vectors): pending → ready; upstream error → failed with a
  message; an image → skipped.

## Manual test plan
1. Set `RAG_ENABLED=true`, `EMBEDDING_MODEL=bge-m3`, run the migration, upload 3 PDFs. The Files page shows
   indexing, then ready.
2. Ask something answered on page 7 of one PDF. The trail shows "Searched your files", and the answer cites
   `[1]`, which on hover shows p. 7 and on click opens the PDF.
3. Arabic question with a spelling variant (اداره vs إدارة) over an Arabic document finds the passage.
4. Ask about an exact contract number. The keyword side finds it.
5. Stop LM Studio's embedding model, upload a file: it fails with a readable error, and Retry works after reloading.
6. `RAG_ENABLED=false`: no tool, no poller, the app works without pgvector installed (the migration still needs
   the extension. Note in README that the migration requires pgvector even when RAG is off, or make the
   migration skip the vector column when the extension is unavailable. **Decide before implementing**, and
   default to requiring it).

## Later (not in this feature)
- Reranking with a cross-encoder (`bge-reranker-v2-m3`) over the top 20 for better precision.
- Per-user HNSW partitioning, or `iterative_scan` (pgvector ≥ 0.8), for large tenants.
- OCR for scanned PDFs (they have no text layer, so they index as `skipped` today).

## Done when
- [ ] All tests pass; `scripts/check.sh` is green.
- [ ] Manual plan 1–6 passes.
- [ ] README has the prerequisites section (pgvector, embedding model, env vars).
