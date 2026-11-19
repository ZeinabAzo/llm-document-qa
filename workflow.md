# Workflow & decision log

This file records **what we did, in what order, and why**: every decision, the alternatives we considered, and the trade-offs we accepted. `CLAUDE.md` describes *what the project is*; this file describes *how we got here*. Add a new dated session at the bottom whenever work continues.

---

## Session 1: audit and full rewrite (2026-11-19)

### Step 1: Audit of the existing code

I read every file and ran the extraction on the real sample document before changing anything. Problems found, grouped by severity:

**Bugs that produced wrong answers**

| # | Problem | Where | Effect |
|---|---|---|---|
| B1 | **Section detection never worked on the sample.** Headings were detected only through Word "Heading N" styles, but the sample handbook uses *bold Normal paragraphs* ("2.1 Paid Time Off") as headings. | `models.py` extraction | Every chunk was labelled "General". The section context the design relied on did not exist. |
| B2 | **Duplicate documents accepted.** The same file had been uploaded 3 times (`documents/` contained 3 identical copies). | upload flow | Each chunk was indexed 3 times, so the top-5 retrieval slots were filled with copies of the same passage. Less real context reached the LLM. |
| B3 | **Source label never reached the LLM.** The prompt asked for `(Source: file.docx - Section)`, but the context only contained `[section, Chunk N]`. | `rag/qa.py` | The model invented or omitted sources. |
| B4 | **Table cells blanked.** Merged-cell dedup compared *text*, so `Yes | Yes` became `Yes | `. | `_extract_table_as_markdown` | Data loss in tables. |
| B5 | **Heading check `startswith("#")`.** Text like `#it-emergency` became a "heading". | `chunking.py` | Wrong sections, lost text. |
| B6 | **BM25 tokenizer kept punctuation.** `policy.` ≠ `policy`. | `retriever.py` | Keyword search missed matches at sentence ends. |
| B7 | **Errors stored as content.** A failed extraction saved `"Error extracting text: ..."` into `extracted_text`. `ask_question` returned "No documents found" as if it were an answer, and the view saved it to history. | `models.py`, `qa.py`, `views.py` | Garbage in the DB and in the history; HTTP 200 for failures. |
| B8 | **No timeout or error handling on the LLM call.** A slow/failed OpenRouter call hung the request or caused a 500. | `qa.py` | Unreliable API. |
| B9 | **1×1 "callout" tables** (banner, "CRITICAL PROTOCOL" box) were turned into one-column Markdown tables with a fake header. | extraction | The most important instruction in the handbook was formatted as a table header. |

**Missing deliverables** (the brief requires them): Docker setup, `requirements.txt`, real REST API (only one `csrf_exempt` endpoint with no auth), API docs, README, tests, sample data, `.env.example`.

**Code quality problems**

- Docx parsing lived inside `models.py`, and ran as a side effect of `save()`, which saved the row twice.
- Module-level mutable globals for the index. Its "is it stale?" check loaded **every document's full text** on every question.
- Similarity `1/(1+L2)` with an arbitrary 0.30 threshold.
- Deprecated imports (`langchain_community.HuggingFaceEmbeddings`). `langchain-community` itself is now officially sunset.
- A new LLM client created per request.
- `MEDIA_ROOT` not set, so uploads landed in the project root `documents/`.
- Hardcoded `SECRET_KEY`, `DEBUG=True`, empty `ALLOWED_HOSTS`. A `MAILERS` setting that doesn't exist in Django 5.2.
- Stale `ai_engine.py` shim, empty `tests.py`, unused `render` import.
- Long paragraphs never split. Overlap took the last 120 *characters*, cutting words in half.

**Decision:** rewrite rather than patch. The structure itself (extraction in the model, globals, no service layer) was the cause of several bugs, and the brief values clean, defendable code.

---

### Step 2: Architecture

**Decision: three layers.**

```
Interfaces (admin.py/forms.py, views.py/serializers.py, management command)
        │  thin: validate input, call a service, format the output
        ▼
services.py   business logic that needs Django (DB, settings)
        │
        ▼
rag/          pure pipeline: extract, chunk, index, prompt/LLM; no Django imports
```

- **Why:** admin and API must behave identically (same validation, same errors). Putting the logic in one place (`services.py`) guarantees that. Keeping `rag/` Django-free makes it unit-testable without a database and easy to explain step by step.
- **Rejected:** "fat models" (logic in `Document.save()`). That hides side effects such as file parsing or network calls inside `save()`, which is surprising and was the cause of the double save.
- **Rejected:** Django signals for extraction. Same problem: invisible side effects. Signals are used only for *file cleanup*, where hooking every delete (including admin bulk delete) is exactly the point.

---

### Step 3: Data model

**`Document`**: `title`, `file`, `extracted_text`, `content_hash` (unique), `created_at`, `updated_at`.

- **Extract at upload time and reject bad files** (instead of storing a "failed" status).
  - *Why:* every saved `Document` is guaranteed to be searchable, and the user sees the problem immediately as a form error or a 400 response. A `.docx` parses in milliseconds, so doing it in the request is fine.
  - *Rejected:* `status`/`error` fields plus background processing. That is more moving parts (Celery or a similar task queue) for no benefit at this scale. It would become worth it for slow formats such as OCR'd PDFs.
- **`content_hash` = SHA-256 of the *extracted text*, not the file bytes.**
  - *Discovered while testing:* a `.docx` stores timestamps inside the file, so saving the same document twice gives different bytes. A byte hash would let duplicates through. A text hash catches "same content, re-saved". A test failed intermittently because of this, and that is how it was found.
  - The `unique=True` constraint is a database-level backstop against race conditions.
- **`title` defaults to the file name.** Users can rename without re-uploading.
- **`updated_at`** exists so the index can detect edits cheaply (see Step 6).

**`QAHistory`**: `question`, `answer`, `sources` (JSON), `model_name`, `latency_ms`, `created_at`.

- `sources` stores the exact passages given to the LLM. This makes every answer **auditable**: you can see why it said what it said. It's also great for the demo.
- `model_name` + `latency_ms` let you compare free models later.
- Only **successful** answers are stored. Failures return an error and store nothing, so the history stays a clean record.
- JSONField instead of a `Source` table: sources are always read together with their answer and never queried on their own, so a separate table adds joins for no benefit.

**Migrations:** the old `0001_initial` was deleted and regenerated. The project was never deployed, so rewriting migration history is safe and gives reviewers one clean migration. **Your old local DB (`db.sqlite3`) and `documents/` folder are no longer used** (the new location is `data/`); delete them whenever you like.

---

### Step 4: Extraction (.docx → Markdown), `rag/extract.py`

- **Markdown as the intermediate format:** it is plain text (easy to store/search/show) but keeps structure: `#` headings, `-` lists, `| |` tables. LLMs read Markdown tables reliably.
- **Heading detection = Word heading style OR "short, fully bold line not ending in punctuation".** The level comes from numbering (`2.1` → level 2), else 1. This fixes B1. It was verified on the real file: 18 chunks with correct section paths like `2. Remote Work & PTO Policy > 2.1 Paid Time Off (PTO) & Holidays`.
  - *Trade-off:* a heuristic can misfire, for example on a bold one-line sentence without a period. Tests cover the important negatives: bold sentence with a period, partly bold paragraph.
- **`document.iter_inner_content()`** (python-docx ≥ 1.0) gives paragraphs and tables in reading order. This replaced ~10 lines of private-API XML iteration.
- **Merged cells deduplicated by identity (`cell._tc`)**, not text. This fixes B4.
- **1×1 tables unwrapped as text** (B9). They are visual boxes, not data.
- **Pipes escaped, whitespace and non-breaking spaces normalized.**
- **Headers/footers skipped:** they repeat on every page and only add noise.

---

### Step 5: Chunking, `rag/chunking.py`

- **Headings are not chunks; they become a "section path" prefixed to each chunk** (`Section: A > B`). A chunk such as "Up to 5 unused days may roll over" is meaningless without knowing it is about PTO, and the prefix gives that context to both the embedding model and the LLM.
- **Heading regex `^#{1,6}\s+`** (B5).
- **Text is split with LangChain's `RecursiveCharacterTextSplitter`.** It tries `\n\n`, then `\n`, then `. `, then space. That gives proper overlap at word/sentence boundaries and splits over-long paragraphs, both of which the old code got wrong.
- **Size 800 chars / overlap 100.** `all-MiniLM-L6-v2` truncates input at **256 tokens (~1000 chars)**; anything beyond is silently ignored when embedding. 800 chars stays safely under that.
- **Tables are never split mid-row.** Large tables are split by rows with the **header repeated** in every part. This was kept from the old code because it was a good idea, then rewritten and tested.

---

### Step 6: Retrieval, `rag/index.py`

**Hybrid search = semantic + keyword, merged with Reciprocal Rank Fusion (RRF).**

- Semantic (embeddings) finds paraphrases: "vacation days" → the PTO section.
- BM25 finds exact tokens such as codes, emails and names: `security-sos@novatech.io`, `NT-OPS-2026-04`.
- RRF: `score = Σ 1/(60 + rank)`. It uses ranks only, so it never compares a cosine similarity with a BM25 score (different scales). This is why the old arbitrary `0.30` threshold was dropped.
- Verified on the real document: "How many vacation days?" → PTO section ranked #1 by both methods. The exact email query → ranked #1 by BM25.

**Vector store: LangChain-core `InMemoryVectorStore` instead of FAISS.**

- *Why:* FAISS lived in `langchain-community`, which is officially sunset. The standalone `langchain-faiss` is a young 0.1 package. `InMemoryVectorStore` ships with `langchain-core`, does **exact** cosine search (exactly what a flat FAISS index does), and adds zero dependencies. For hundreds or thousands of chunks it takes milliseconds (measured: 17 ms per question including BM25).
- *Trade-off / scaling path:* for very large corpora, swap in FAISS-HNSW or pgvector behind the same LangChain `VectorStore` interface. `HybridIndex` would only change in its constructor.

**BM25: kept as our own ~25-line class** (cleaned up and precomputed) instead of the `rank_bm25` package.

- *Why:* `rank_bm25`'s Okapi variant can produce **negative IDF** for words appearing in more than half the chunks, which is common in small corpora. The Lucene IDF `log(1 + (N-df+0.5)/(df+0.5))` is always positive. Owning 25 lines that you can explain is better than a dependency with a quirk.
- Tokenizer fixed (B6): keeps `a@b.io`, `nt-ops-2026-04` and `2.1` whole, and drops trailing punctuation.

**Index lifecycle, `services.DocumentIndex`:**

- One in-memory index per process. Before each question, **one aggregate query** (`COUNT(id), MAX(updated_at)`) detects whether documents were added, edited or deleted. Only then is the index rebuilt. The old code loaded every document's full text on every question.
- A `threading.Lock` stops two concurrent requests from rebuilding at the same time.
- `HybridIndex` is immutable once built. A rebuild creates a new object and swaps it in, so readers never see a half-built index.
- *Trade-off:* every change rebuilds everything (re-embeds all chunks). That's fine at this scale (the sample takes under a second once the model is loaded). Next step: incremental indexing / persisted embeddings.

**Embedding model `all-MiniLM-L6-v2` (local).** Free, about 90 MB, fast on CPU, and documents are never sent to a third party for indexing. Imported **lazily**, because importing it loads PyTorch (seconds), and every `manage.py` command would otherwise pay that cost.

---

### Step 7: Answer generation, `rag/qa.py` + `services.answer_question`

- **LCEL chain `prompt | llm | StrOutputParser()`.** This is the idiomatic LangChain way and is easy to swap or test.
- **Prompt rules:** only use the passages, the exact fallback sentence otherwise, cite as `[n]`, answer in the question's language.
- **Passages are numbered `[1]..[k]` and labelled with the document title** (fixes B3). The API returns `sources` with the same numbers, so a client can link each `[n]` to its passage. Asking the model to *cite numbers* is more reliable than asking it to *copy file names*.
- **temperature 0.1:** factual extraction, not creativity.
- **LLM client created once** (`lru_cache`), with `timeout=60s` and `max_retries=2`. All provider errors become an `LLMError` → HTTP **502** (fixes B8). Missing API key → clear message instead of a crash.
- **Verified live with OpenRouter:**
  - PTO question → correct, cited answer.
  - Kestrel question → answered from the table.
  - "Capital of France?" → exact fallback sentence. No hallucination.

---

### Step 8: REST API (Django REST Framework + drf-spectacular)

- **Endpoints:**
  - `documents/`: full CRUD via `ModelViewSet`.
  - `ask/`: POST.
  - `history/`: read-only.
  - `health/`.
  - `schema/`, `docs/`, `redoc/`.
- **Why DRF:** the standard for Django APIs. Validation, pagination, auth, throttling and OpenAPI generation come for free, with far less code than hand-written `JsonResponse` views.
- **Auth: Session + Basic, `IsAuthenticated` by default.**
  - *Why:* the API can upload and delete files and spend LLM quota, so it should not be public.
  - Basic auth makes `curl -u` trivial for reviewers. Session auth makes Swagger work after an admin login.
  - The docs pages are public because the schema is not secret.
  - *Rejected:* token/JWT auth. It adds setup steps that don't matter for this assignment and is easy to add later.
- **Status codes:**
  - `201` for ask: it creates a history record.
  - `409` when there are no documents: the request is valid, but the server state doesn't allow it.
  - `502` when the LLM fails: an upstream failure, not our bug.
  - `429` from throttling.
- **Rate limit 20/min per user on `ask`:** each call spends LLM quota, and free OpenRouter models have strict limits.
- **List view doesn't load `extracted_text`.** It uses `.defer()` plus a SQL `Length()` annotation, so listing 100 large documents stays cheap.
- **`file` URLs** are served only to logged-in staff (documents are private). Fine at this scale; production would use a proper file server or signed URLs.

---

### Step 9: Admin (the only UI)

- **Documents:** list with character count, search over title and text, extracted Markdown shown read-only. Upload errors (duplicate, corrupt, empty) appear **inline on the form**.
- **Asking from the admin:** the "Add Q&A history entry" page *is* the question form. The answer is generated during form validation, so if the LLM fails the admin shows an error and saves nothing.
  - *Why:* the brief says the admin is the only UI, so a user must be able to perform feature 4, "submit a question", there.
- **History is view-only** (`has_change_permission=False`): it's a record of what happened. Sources are rendered as readable passages.

---

### Step 10: Configuration, Docker, deployment

- **All config from environment variables** (`.env` for local development). Secure defaults: `DEBUG` off, and the app refuses to start without `DJANGO_SECRET_KEY` unless DEBUG is on.
- **One data directory (`DATA_DIR`)** for SQLite and uploads, so Docker needs one volume.
- **SQLite** (not PostgreSQL). One instance, low write volume, zero setup for reviewers. Moving to Postgres is a settings change; mention it as the scaling step.
- **Dockerfile:**
  - CPU-only PyTorch (~10× smaller).
  - Embedding model downloaded **at build time**, with `HF_HUB_OFFLINE=1` at runtime, so startup doesn't depend on HuggingFace being reachable.
  - Dependencies installed in their own layer, so code changes rebuild in seconds.
  - Runs as a non-root user.
  - Health check.
  - `whitenoise` serves the admin CSS without nginx.
- **gunicorn: 1 worker, 4 threads.** Each worker *process* would hold its own copy of the model and index (memory × N, plus N rebuilds). Threads share them, and the GIL is not a problem because requests mostly wait on network I/O (the LLM).
- **Entrypoint:** migrate → create the admin user from env (first start only) → optionally load the sample data → start the server.
- **`.gitattributes` forces LF for `*.sh`.** A Windows CRLF line ending would break the script inside the Linux container.
- **Note:** Docker is not installed on the development machine, so the image could not be built here. The same `requirements.txt` was installed into a **fresh virtualenv** and the full test suite run there, to validate the dependency list.

---

### Step 11: Tests (54, offline, about 15 s)

- **`test_extract`:** heading styles, bold numbered headings, bold-sentence negatives, `#it-emergency`, lists, repeated table values (B4), merged cells, pipe escaping, callout tables, reading order.
- **`test_chunking`:** section paths, preamble, empty headings, long-paragraph splitting, metadata, table detection and splitting (no rows lost or duplicated).
- **`test_index`:** tokenizer, BM25 (including the negative-IDF case), RRF arithmetic, hybrid search.
- **`test_api`:** auth, public docs, upload/duplicate/corrupt/extension, list vs detail, rename, file replacement deletes the old file, delete removes the file, ask (answer, sources, history), keyword retrieval, index refresh after new upload, 409, 502, validation, history, admin pages, admin ask and admin errors.
- **Fakes:** `DeterministicFakeEmbedding` and `FakeListChatModel` from `langchain-core`. They make tests fast, free, deterministic and runnable without an API key.

---

### Things that need *you*

1. **Screenshots** of the admin: list in `docs/screenshots/README.md`.
2. **Build and run Docker once** (`docker compose up --build`) on a machine with Docker. It could not be done here.
3. **Delete the old `db.sqlite3` and `documents/`** in the project root (no longer used, already git-ignored).
4. **Check the original brief** for the API list that was missing from your copy ("at least the following").
5. **Commit** the work. Suggested message: `refactor: rewrite RAG pipeline, add REST API, Docker, tests and docs`.
6. Optional: try a few other free models via `OPENROUTER_MODEL` and pick the most reliable one for the demo.

### Presentation cheat sheet (10 minutes)

1. Demo (4 min):
   - `docker compose up`.
   - Admin → document → extracted Markdown (show detected sections and tables).
   - Ask the PTO question → show the cited source.
   - Ask a table question → show the cited source.
   - Ask an off-topic question → fallback answer.
   - Upload a duplicate → inline error.
   - Swagger.
2. Architecture (3 min): the three-layer diagram in the README, and the upload and question flows.
3. Decisions (3 min): hybrid + RRF, heading detection discovered from the real file, text hash for duplicates, in-memory index with a cheap staleness check, strict prompt with numbered citations, 1 worker + threads. For each, the trade-off and what you'd do at scale.

---

## Session 2: test documents and question set (2026-11-19)

**Goal:** give you realistic material to test and demo with, beyond the single sample handbook.

**What was added** (`test_documents/`):

| File | Deliberately tests |
|---|---|
| `Aurora_Cloud_Hosting_Service_Guide.docx` | Real Word heading styles (the other documents use fake bold headings, so both code paths of heading detection run), a table with repeated `Yes \| Yes` values (bug B4), a horizontally merged table row |
| `Meridian_Clinic_Patient_Policy.docx` | Bold numbered fake headings, a 1x1 callout box (bug B9), exact identifiers (form code, email, phone numbers: the case where BM25 matters), a directory table |
| `Lindqvist_Foundation_Board_Minutes.docx` | **No headings at all.** Every chunk gets an empty section; checks that nothing relies on headings existing |
| `QUESTIONS.md` | 28 questions with expected answers, grouped by what each tests |
| `build_test_documents.py` | Regenerates the three files, so the content is reviewable as code |

**Decisions**

- **Separate folder, not `sample_data/`.** `load_sample_data` (and the Docker entrypoint with `LOAD_SAMPLE_DATA=1`) uploads everything in `sample_data/`. Reviewers should start with one clean document, so test material lives apart and is uploaded by hand.
- **Fictional content with unambiguous facts.** Each question has exactly one correct answer, so a pass/fail is objective. Some are deliberately tricky rather than easy:
  - *Name collision:* "Project Meridian" (NovaTech) vs "Meridian Clinic". Retrieval must pick the right document.
  - *Needs inference or arithmetic:* "14-year-old alone?" and the 0.3% uptime credit.
  - *Looks like a gap but is not:* "price of Enterprise" is answered ("custom quote"). A good system must not fall back here.
  - *Looks answerable but is not:* "Who voted against Hamburg?" (only the count is given), and "Clara Dubois's job title" (only named in the apologies). These check that the model does not guess.
- **Verified for real, not assumed.** I loaded all four documents into a throwaway database (so your data was not touched) and ran all 28 questions through the real embeddings and the real OpenRouter model: **28/28 behaved as expected** (24 correct answers, 4 correct fallbacks). The expected answers in `QUESTIONS.md` are therefore observed behaviour, not guesses.

**Caveat to remember:** answers come from a free LLM, so wording varies between runs and a different model may fail a tricky question (the arithmetic one is the most likely). Treat the facts as the pass criterion, not the exact sentence.

---

## Session 3: usage guide and terminal `ask` command (2026-11-19)

**Problem:** asking a question from PowerShell through the API was awkward: `curl` is an alias for a different command there, JSON quotes need escaping, and Basic auth needs a Base64 header. That's too much friction for daily testing, and for a live demo.

**What was added**

- **`python manage.py ask`**: a management command that calls `services.ask()` directly.
  - `ask "question"` answers once. `ask` with no question opens an interactive prompt that keeps asking until an empty line.
  - Prints the answer, the numbered sources (document > section) and the latency, and saves to `QAHistory` like the API does.
  - *Why a management command, not a script:* it reuses Django's settings, database and the same service function as the admin and API, so behaviour is identical. It's ~40 lines and needs no new dependency.
  - *Why interactive mode:* the embedding model and index load once per process (10–20 s). In one long-running prompt only the first question pays that, so later questions take ~3 s.
  - *Errors:* in single-question mode they raise `CommandError` (non-zero exit code, script-friendly). In interactive mode they're printed and the prompt continues.
  - It bypasses HTTP auth on purpose: anyone who can run `manage.py` already has full access to the database.
- **3 tests** (`AskCommandTests`): answer + sources + history saved, no-documents error, interactive loop. Suite: 57 tests.
- **`HOW_TO_USE.md`**: copy-paste guide for Windows PowerShell. Covers: start, ask in the terminal, admin click-paths, API (Swagger, `Invoke-RestMethod`, `curl.exe`), useful commands, and a "you see → it means → do this" troubleshooting table.
  - *Separate from the README:* the README is for reviewers (what and why); this file is for using it day to day (how). Linked from the top of the README.
  - No real usernames or passwords in the file; it uses placeholders.

**Verified:** `manage.py ask "Which insurers does the clinic accept?"` against the real model in a throwaway database returned the correct cited answer.

---

## Session 4: simplification and cleanup (2026-11-19)

**Question asked:** is the project more complicated than it needs to be? I measured it instead of guessing.

**Finding:** the code is already lean. The whole pipeline (`rag/`: extract, chunking, index, qa) is about 400 lines, `services.py` about 250, and nothing is duplicated. The clutter was leftover files, not architecture. I kept everything the brief requires (admin, API, Docker, hybrid retrieval, history) and the extras that earn their place (duplicate detection, file cleanup on delete, rate limit, health check for Docker).

**Deleted**

| What | Why |
|---|---|
| `db.sqlite3`, `documents/` in the project root | Pre-rewrite leftovers. The app now uses `data/`. The old database held only one test document and three test Q&A entries (and the old login) |
| `staticfiles/` (4.2 MB) | Generated by my `collectstatic` smoke test. Git-ignored and rebuilt automatically in Docker |
| `test_documents/build_test_documents.py` | A second thing to maintain. The finished `.docx` files and `QUESTIONS.md` are what matter. (Still in git history if ever needed) |
| `docs/screenshots/README.md` | A placeholder. The list of screenshots to take now lives in one line of `CLAUDE.md` open items |

**Simplified**

- `services.get_llm()` and `services.get_answer_chain()` merged into one cached `get_answer_chain()`. `get_llm` had a single caller and no tests used it, so it was an extra layer for nothing. Also removed the now-unused `BaseChatModel` import.

**Considered and kept**

- Documents: `README.md`, `CLAUDE.md`, `workflow.md`, `document.md`, `HOW_TO_USE.md`, `docs/API.md` and `test_documents/QUESTIONS.md` each have a different reader and purpose. `CLAUDE.md`, `workflow.md` and `document.md` were explicitly required, and `HOW_TO_USE.md` was already cut to one screen.
- `ParsedUpload` / `apply_parsed_upload`: three callers (admin form, API serializer, sample loader) share it, which is what keeps their validation identical.
- Index rank fields (`vector_rank`, `keyword_rank`): small, and valuable in the demo to show how hybrid search found each passage.

**Verified:** 57 tests pass, and a real question through the merged function returned a correct answer.
