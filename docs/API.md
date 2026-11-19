# API reference

Base URL: `http://localhost:8000/api/`

Interactive docs generated from the code (always up to date):

- Swagger UI: `/api/docs/` (try requests in the browser; use **Authorize** → Basic auth, or log in to the admin first)
- ReDoc: `/api/redoc/`
- OpenAPI 3 schema (YAML): `/api/schema/`

## Authentication

Every endpoint except `/api/health/` and the documentation requires an authenticated user:

- **HTTP Basic**: `curl -u admin:PASSWORD ...`
- **Session**: if you are logged in to `/admin/`, the browser and Swagger UI are already authenticated.

Unauthenticated requests get `403 {"detail": "Authentication credentials were not provided."}`.

## Conventions

- Request and response bodies are JSON, except file uploads, which use `multipart/form-data`.
- Lists are paginated: `{"count", "next", "previous", "results"}`, 20 items per page, `?page=N`.
- Errors:
  - Validation errors return `400` with field names as keys: `{"file": ["This document was already uploaded as \"x.docx\" (id 3)."]}`
  - Other errors return `{"detail": "message"}`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/documents/` | List documents |
| `POST` | `/api/documents/` | Upload a `.docx` |
| `GET` | `/api/documents/{id}/` | Get a document including its extracted text |
| `PATCH` | `/api/documents/{id}/` | Rename and/or replace the file |
| `PUT` | `/api/documents/{id}/` | Replace title and file |
| `DELETE` | `/api/documents/{id}/` | Delete the document and its file |
| `POST` | `/api/ask/` | Ask a question (saved to history) |
| `GET` | `/api/history/` | List questions and answers, newest first |
| `GET` | `/api/history/{id}/` | Get one question and answer |
| `GET` | `/api/health/` | Health check (no auth) |

---

### `POST /api/documents/`: upload

`multipart/form-data` fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | `.docx`, at most `MAX_UPLOAD_SIZE_MB` (10 MB) |
| `title` | string | no | Defaults to the file name |

```bash
curl -u admin:PASSWORD -F "file=@sample_data/NovaTech_Solutions_Employee_IT_Handbook_2026.docx" \
     -F "title=Employee Handbook" http://localhost:8000/api/documents/
```

`201 Created`

```json
{
  "id": 1,
  "title": "Employee Handbook",
  "file": "http://localhost:8000/media/documents/NovaTech_Solutions_Employee_IT_Handbook_2026.docx",
  "content_hash": "4f1c...e9",
  "text_length": 9876,
  "created_at": "2026-11-19T14:30:00Z",
  "updated_at": "2026-11-19T14:30:00Z"
}
```

`400 Bad Request` when:

| Situation | Message (in `file`) |
|---|---|
| Wrong extension | `File extension "pdf" is not allowed. Allowed extensions are: docx.` |
| Not a real .docx | `Could not read this file. Is it a valid .docx document?` |
| No text inside | `The document contains no text.` |
| Same text already uploaded | `This document was already uploaded as "..." (id N).` |
| Too large | `File is larger than 10 MB.` |

The text is extracted during the request, so a document that is saved is always searchable. The `file` URL can be downloaded by logged-in staff.

### `GET /api/documents/`: list

`200 OK`: paginated list of the objects above. Without `extracted_text`, which can be large; `text_length` gives its size.

### `GET /api/documents/{id}/`: detail

Same fields plus `extracted_text`, the full document as Markdown (headings as `#`, lists as `-`, tables as `| ... |`).

### `PATCH /api/documents/{id}/`: edit

Rename (JSON):

```bash
curl -u admin:PASSWORD -X PATCH -H "Content-Type: application/json" \
     -d '{"title": "Handbook 2026"}' http://localhost:8000/api/documents/1/
```

Replace the file (multipart). The text is re-extracted and the old file is deleted from disk:

```bash
curl -u admin:PASSWORD -X PATCH -F "file=@new_version.docx" http://localhost:8000/api/documents/1/
```

`200 OK` with the updated document. Same `400` errors as upload. The search index updates automatically before the next question.

### `DELETE /api/documents/{id}/`

`204 No Content`. The file is removed from disk and the document stops appearing in answers.

---

### `POST /api/ask/`: ask a question

| Field | Type | Required | Notes |
|---|---|---|---|
| `question` | string | yes | 1–2000 characters, surrounding whitespace is trimmed |
| `top_k` | integer | no | Passages to retrieve, 1–20 (default `RETRIEVAL_TOP_K` = 5) |

```bash
curl -u admin:PASSWORD -H "Content-Type: application/json" \
     -d '{"question": "Who leads Project Kestrel and when does it launch?"}' \
     http://localhost:8000/api/ask/
```

`201 Created`. The answer is saved as a history entry and returned:

```json
{
  "id": 7,
  "question": "Who leads Project Kestrel and when does it launch?",
  "answer": "The lead engineer of Project Kestrel is Maya Lin-Sato, and its target launch date is October 14, 2026 (Q4) [2].",
  "sources": [
    {
      "number": 1,
      "document_id": 1,
      "document_title": "Employee Handbook",
      "section": "5. 2026 Internal Project Code Names & Deadlines > 5.1 Milestone & Release Governance",
      "excerpt": "Section: 5. 2026 Internal Project Code Names & Deadlines > 5.1 ...",
      "score": 0.0328,
      "vector_rank": 1,
      "keyword_rank": 1
    },
    {
      "number": 2,
      "document_id": 1,
      "document_title": "Employee Handbook",
      "section": "5. 2026 Internal Project Code Names & Deadlines",
      "excerpt": "Section: 5. 2026 Internal Project Code Names & Deadlines\n| Code Name | Lead Engineer | Target Launch Date | Scope & Deliverable |\n| --- | --- | --- | --- |\n| Project Helios | ...",
      "score": 0.032,
      "vector_rank": 2,
      "keyword_rank": 3
    }
  ],
  "model_name": "nvidia/nemotron-3-ultra-550b-a55b:free",
  "latency_ms": 2783,
  "created_at": "2026-11-19T14:33:08Z"
}
```

Fields in each `sources` item:

| Field | Meaning |
|---|---|
| `number` | The `[n]` used for citations in `answer` |
| `section` | Heading path inside the document |
| `excerpt` | The exact passage text given to the LLM |
| `score` | Reciprocal Rank Fusion score, higher is better |
| `vector_rank` | Rank in semantic (embedding) search, `null` if not in the top 20 |
| `keyword_rank` | Rank in BM25 keyword search, `null` if no shared keywords |

If the documents don't contain the answer, `answer` is exactly:
`I don't have enough information in the provided documents to answer this question.`

Errors:

| Status | When | Body |
|---|---|---|
| `400` | Empty question, `top_k` out of range | `{"question": ["This field may not be blank."]}` |
| `409` | No documents uploaded yet | `{"detail": "No documents have been uploaded yet."}` |
| `429` | More than `ASK_RATE_LIMIT` (20/min) questions | `{"detail": "Request was throttled. Expected available in N seconds."}` |
| `502` | LLM provider error or timeout | `{"detail": "The language model is unavailable right now. Please try again."}` |
| `502` | `OPENROUTER_API_KEY` not set | `{"detail": "The LLM is not configured: set OPENROUTER_API_KEY."}` |

Failed questions are **not** saved to the history.

---

### `GET /api/history/`

`200 OK`: paginated list of the objects returned by `/api/ask/`, newest first.

### `GET /api/history/{id}/`

`200 OK`: one entry. History is read-only through the API; entries can be deleted in the admin.

### `GET /api/health/`

`200 OK {"status": "ok"}`. No authentication and no LLM call. Used by the Docker health check.
