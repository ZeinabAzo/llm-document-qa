# LLM Document QA

A Django project that lets users upload `.docx` documents and ask questions answered **only from those documents**, using LangChain + an LLM via OpenRouter. This is a time-boxed hiring assignment (7 calendar days), followed by a ~10 minute walkthrough where I must explain the architecture and defend every technical decision. **Simple, readable code beats clever code.**

## Project documents: keep them separate

| File | Contains | Update when |
|---|---|---|
| `CLAUDE.md` (this file) | What the project is: requirements, architecture, conventions, current status | The structure or status changes |
| `workflow.md` | Decision log: what was done, in which order, why, alternatives rejected | **Every work session**, with a new dated section at the bottom |
| `document.md` | Learning notes: concepts behind the code, likely interview questions | A new concept/technique is introduced |
| `README.md` | Reviewer-facing: setup, usage, architecture summary | Setup or features change |
| `HOW_TO_USE.md` | Copy-paste daily usage guide (PowerShell), troubleshooting table | Commands or UI flows change |
| `test_documents/QUESTIONS.md` | Test documents + 28 verified questions with expected answers | Test documents change |
| `docs/API.md` | API reference | Endpoints change |

Working rules from the project owner:
1. Always explain deeply what is done and log it in `workflow.md`.
2. This is a hiring challenge: production-quality, but no unnecessary complexity.
3. Keep `document.md` growing as a learning resource.

## Assignment requirements (source of truth)

Hard requirements:
- **Django** is mandatory.
- Must run with **Docker** (Dockerfile + docker-compose).
- **LangChain** is mandatory for the processing flow and LLM communication.
- Must expose a **complete, usable API**.
- The UI is the **Django Admin** only. No separate frontend.
- Any library, LLM or architecture is allowed otherwise.

Minimum features:
1. Add, edit, delete documents
2. `.docx` support
3. Store the full extracted text of each document
4. Submit a question
5. Find content relevant to the question
6. Advanced retrieval for accurate answers (hybrid retrieval counts)
7. Generate a text answer grounded in the documents
8. Store the history of questions and answers

Free LLM: OpenRouter, a model from https://openrouter.ai/collections/free-models

Deliverables (a single zip):
- [x] Source code
- [x] `Dockerfile` and `docker-compose.yml` (**built and tested** on the dev machine on 2026-11-19: admin, static files, API auth, a real question, data survives restart)
- [x] `README.md` with setup steps
- [ ] Screenshots of the admin panel (save them in `docs/screenshots/`)
- [x] API documentation (`docs/API.md` + Swagger at `/api/docs/`)
- [x] Sample data (`sample_data/NovaTech_Solutions_Employee_IT_Handbook_2026.docx`)

> The brief says the API should include "at least the following", but the list is missing from my copy. Current API: documents CRUD, ask, history list/detail, health. Confirm against the original brief if possible.

## Architecture

```
admin.py / forms.py      ─┐
views.py / serializers.py ─┼─► services.py ─► models.py (Document, QAHistory; SQLite)
management/commands/      ─┘        │
                                    ▼
                    rag/  (no Django imports)
                      extract.py   .docx -> Markdown (headings by style OR bold numbered line;
                                   tables by row with merged-cell dedup; 1x1 tables -> text)
                      chunking.py  section path prefix; RecursiveCharacterTextSplitter (800/100);
                                   tables split by row with header repeated
                      index.py     HybridIndex: InMemoryVectorStore (cosine) + own BM25, fused by RRF (k=60)
                      qa.py        ChatPromptTemplate | ChatOpenAI(OpenRouter) | StrOutputParser
```

- **Upload:** `services.parse_docx_upload` validates size, extracts text, rejects unreadable/empty files and duplicates (SHA-256 of the *extracted text*). Used by both `DocumentAdminForm` and `DocumentSerializer`.
- **Question:** `services.answer_question` → `document_index.get()` (rebuilds only if `COUNT`/`MAX(updated_at)` changed) → `HybridIndex.search` → LLM chain → `Answer`. `services.ask` also saves `QAHistory`.
- **Errors:** `NoDocumentsError` → 409, `LLMError` → 502. Failures are never saved to history.
- **API:** DRF + drf-spectacular. Session + Basic auth, `IsAuthenticated`. `/api/ask/` throttled.
- **Admin:** "Add Q&A history entry" is the ask-a-question form; history is view-only.
- **Config:** env vars only (`.env` locally, see `.env.example`). Data (DB + media) under `DATA_DIR` (default `./data`).
- **Docker:** python:3.11-slim, CPU torch, embedding model baked in (`HF_HUB_OFFLINE=1`), gunicorn 1 worker × 4 threads, entrypoint migrates/creates admin/loads sample.

## Commands

```bash
venv/Scripts/python.exe manage.py runserver            # needs DJANGO_DEBUG=1 or DJANGO_SECRET_KEY in .env
venv/Scripts/python.exe manage.py test rag_app         # 57 tests, offline (fake LLM + fake embeddings)
venv/Scripts/python.exe manage.py load_sample_data
venv/Scripts/python.exe manage.py ask "question"       # ask from the terminal (no args = interactive)
venv/Scripts/python.exe manage.py spectacular --validate --fail-on-warn > /dev/null   # check OpenAPI schema
docker compose up --build
```

## Conventions

- Keep it simple: plain functions and small classes, minimal abstraction, short docstrings that explain *why*.
- Views/admin stay thin; logic goes in `services.py`; `rag/` must not import Django.
- Don't add dependencies without a clear reason (and write the reason in `workflow.md`).
- Type hints on public functions.
- The answer prompt must stay strict: answer only from context, return the fixed fallback sentence otherwise, cite `[n]`.
- Tests must not call the network: use `tests/helpers.fake_rag()`.
- Never commit `.env` or API keys.

## Open items

1. Take admin screenshots into `docs/screenshots/`: documents list, a document's extracted text, the ask form, an answer with sources, the history list, Swagger (`/api/docs/`).
2. Optionally compare a few free OpenRouter models for answer quality and citation reliability.
3. Possible improvements (talk about these rather than build them): cross-encoder reranking, persisted/incremental embeddings (pgvector), PDF support, an evaluation question set.
