# Learning notes

Concepts used in this project, explained from the ground up, each linked to the code that uses it. Read it top to bottom once, then use it as a reference. Every section ends with **"Likely interview questions"**.

---

## 1. RAG: Retrieval-Augmented Generation

**Problem:** an LLM doesn't know your private documents, and if you ask it anyway it may confidently invent an answer ("hallucinate"). You also can't paste 500 pages into every prompt: it's slow, expensive, and models get worse at finding facts in very long contexts.

**Idea:** before asking the LLM, **retrieve** the few passages most relevant to the question, and give the LLM *only those* with the instruction "answer only from this".

```
question ──► retrieve top-k passages ──► prompt = rules + passages + question ──► LLM ──► answer
```

Two halves, each of which can fail on its own:

- **Retrieval quality:** if the right passage isn't retrieved, the LLM can't answer. Most of this project's effort (extraction, chunking, hybrid search) goes into this half.
- **Generation faithfulness:** if the passage *is* there, the LLM must use it and nothing else. That's the prompt's job (`rag_app/rag/qa.py`).

**Likely interview questions**

- *Why not fine-tune the model on the documents?* Fine-tuning is expensive and slow to update, can't cite sources, and still hallucinates. RAG updates instantly when a document changes and every answer is traceable to passages.
- *How do you know if a bad answer is a retrieval or a generation problem?* Look at `sources` in the history. If the right passage is there, the problem is generation (prompt/model). If not, it's retrieval.

---

## 2. Extracting text from .docx (`rag/extract.py`)

A `.docx` is a **zip file of XML documents**. `python-docx` parses it into Python objects: `Paragraph` (text + style + runs) and `Table` (rows → cells).

- A **run** is a stretch of text with the same formatting. "**Stipend:** every hire gets $1,200" is two runs: a bold one and a normal one.
- A **style** is a named format such as "Normal", "Heading 1" or "List Bullet".

**Lesson learned from the sample document:** its headings are *not* "Heading" styles. They are Normal paragraphs where every run is bold. Code that only checks styles silently finds no headings. **Always inspect real input data before trusting a parser.** That's how this bug was found:

```python
for p in doc.paragraphs:
    print(p.style.name, [(r.bold, r.font.size) for r in p.runs], p.text[:50])
```

**Merged cells:** in Word XML, a cell spanning 2 columns is *one* element (`<w:tc>`), but `row.cells` returns it once per grid column. Comparing `cell._tc` **identity** (is it the same object?) detects real merges. Comparing **text** wrongly removes two genuine cells that happen to say "Yes".

**Why Markdown output:** it's text (storable, searchable, readable in the admin), but it keeps the structure the next steps need: `#` headings for sections and `|` tables for tabular data.

**Likely interview questions**

- *What do you lose?* Images, text boxes, footnotes, headers/footers, comments and tracked changes. Bold/italic inside paragraphs too, which barely matters for QA.
- *How would you add PDF?* Write `pdf_to_markdown()` (for example with `pymupdf4llm`). Everything after extraction is format-agnostic.

---

## 3. Chunking (`rag/chunking.py`)

**Why split documents?** Retrieval returns *passages*, not documents. Passages should be small enough to be **about one thing**, so search precision is high and the LLM isn't flooded, and big enough to contain a **complete fact**.

**Why ~800 characters?** The embedding model (`all-MiniLM-L6-v2`) reads at most **256 tokens** (~1000 characters of English). It *silently ignores* the rest. A 3000-character chunk would be embedded based only on its first third.

**Overlap (100 chars):** neighbouring chunks share a little text, so a sentence cut at a boundary still appears whole in one of them.

**`RecursiveCharacterTextSplitter`** (LangChain) tries separators in order (`\n\n` paragraph → `\n` line → `. ` sentence → ` ` word) and uses the biggest one that makes pieces fit. Text is cut at natural boundaries rather than mid-word.

**Section path prefix:** each chunk starts with `Section: 2. Remote Work & PTO Policy > 2.1 Paid Time Off`. Without it, a chunk saying "up to 5 days may roll over" doesn't say *what* rolls over. The prefix fixes that for both the search and the LLM. This is a cheap form of **contextual chunk headers**.

**Tables:** a table row is meaningless without its header (`| Project Kestrel | Maya Lin-Sato |`: which column is which?). So tables are split by **whole rows**, and every part **repeats the header**.

**Likely interview questions**

- *How did you pick chunk size?* From the embedding model's token limit, then by checking that the sample's chunks were coherent. With more time: an evaluation set, measuring retrieval hit-rate for several sizes.
- *Semantic chunking?* Splitting where the embedding similarity between sentences drops. It's more compute for an uncertain gain; this document's headings already give natural boundaries.

---

## 4. Embeddings and semantic search

An **embedding model** maps text to a vector (here, 384 numbers) so that texts with similar *meaning* get vectors pointing in similar directions.

- **Cosine similarity** = cos(angle between vectors). 1 means the same direction (very similar), 0 means unrelated.
- **Semantic search:** embed the question, compare it with every chunk's vector, and return the most similar chunks.
- "How many vacation days do I get?" matches "22 days of Paid Time Off" even with **no shared keywords**. That's the strength.
- **Weakness:** exact identifiers. `NT-OPS-2026-04` or an email address carry little "meaning", so their embeddings are fuzzy.

**`InMemoryVectorStore`** (langchain-core) keeps all vectors in a list and computes cosine similarity against every one (**exact / brute-force search**). For thousands of chunks that takes milliseconds. Vector databases (FAISS-HNSW, pgvector, Qdrant…) use **approximate nearest neighbour** indexes that make search fast for *millions* of vectors, at the cost of occasionally missing the true best match. We don't need that at this scale.

**Local model vs API embeddings:** local is free, private (documents never leave the server) and has no rate limits. API models (OpenAI, Cohere…) are more accurate and multilingual, but cost money and send your data out.

**Likely interview questions**

- *Why `all-MiniLM-L6-v2`?* Small (~90 MB), fast on CPU, strong for English retrieval, and the default in sentence-transformers. A larger model like `bge-base` or a multilingual one could replace it via `EMBEDDING_MODEL` with no code change.
- *What happens if you change the embedding model?* All chunks must be re-embedded. Vectors from different models aren't comparable. Here that happens automatically on restart because the index is built in memory.

---

## 5. BM25: keyword search (`rag/index.py`, class `BM25`)

BM25 is the classic search-engine ranking function, used by Elasticsearch and Lucene. For each query word that appears in a chunk, it adds:

```
IDF(word) × tf × (k1 + 1) / (tf + k1 × (1 − b + b × chunk_length / avg_length))
```

- **tf** (term frequency): how often the word appears in the chunk. More occurrences means more relevant, but with **diminishing returns** controlled by `k1 = 1.5`. The 10th "policy" adds much less than the 1st.
- **IDF** (inverse document frequency): rare words matter more. "Kestrel" (in 2 chunks) is far more informative than "the" (in all of them). We use Lucene's formula `log(1 + (N − df + 0.5)/(df + 0.5))`, which is never negative.
- **Length normalisation** (`b = 0.75`): a long chunk mentions everything a bit, so its score is scaled down.

**Tokenizer:** lower-case, then keep `a-z0-9` words joined by `.` `_` `-` `@`, so `security-sos@novatech.io` and `nt-ops-2026-04` stay one token, and the trailing `.` of a sentence is dropped.

**Likely interview questions**

- *Why implement BM25 yourself?* It's 25 lines, and the popular `rank_bm25` package's Okapi IDF goes negative for words in more than half the chunks. That's a real problem with small corpora.
- *Stemming / stop words?* Not used. IDF already makes common words nearly worthless, and stemming ("policies" → "polici") helps recall but sometimes hurts precision. Easy to add to `tokenize()`.

---

## 6. Hybrid search and Reciprocal Rank Fusion

Semantic and keyword search fail on *different* questions, so we run **both** and merge them.

**The merging problem:** cosine similarity is in [−1, 1], while BM25 scores are unbounded (3.2, 17.8…). Adding them is meaningless, and normalising them is fragile.

**RRF ignores scores and uses only ranks:**

```
RRF(chunk) = Σ over each result list of 1 / (60 + rank of the chunk in that list)
```

- A chunk ranked #1 semantically and #1 by keywords gets 1/61 + 1/61 = 0.0328 (the maximum).
- A chunk ranked #1 in only one list gets 1/61 = 0.0164.
- Being found by **both** methods beats being first in just one. That's the behaviour we want.
- **k = 60** comes from the original paper (Cormack et al., 2009). It dampens the difference between rank 1 and rank 2 so that no single list dominates.

The `vector_rank` and `keyword_rank` fields in the API's `sources` show exactly how each passage was found. That's useful in the demo.

**Likely interview questions**

- *Why not a weighted sum of normalised scores?* The weights need tuning and the normalisation depends on the score distribution of each query. RRF has no parameters to tune, and it's robust.
- *What's next for retrieval quality?* A **cross-encoder reranker**: re-score the fused top-20 with a model that reads question and passage *together*. It's more accurate than embeddings but too slow to run on every chunk.

---

## 7. The prompt and the LLM call (`rag/qa.py`, `services.answer_question`)

**Prompt rules:** only the passages, the exact fallback sentence otherwise, cite as `[n]`.

- The **fixed fallback sentence** makes "I don't know" machine-detectable and consistent.
- **Numbered passages + `[n]` citations:** models copy numbers reliably. The API returns `sources` with the same numbers, so the citation can be checked.
- **System vs human message:** rules go in the system message, which models weight more strongly. Data (passages and question) goes in the human message.
- **Temperature 0.1:** temperature controls randomness. For extracting facts, we want the most likely wording, not creativity.

**LCEL (LangChain Expression Language):** `PROMPT | llm | StrOutputParser()` builds a pipeline. `.invoke({"context": ..., "question": ...})` fills the template, calls the model and returns the text. Every piece is replaceable, which is how tests swap in `FakeListChatModel`.

**OpenRouter:** one API key gives access to many models, and it speaks the **OpenAI API format**, so LangChain's `ChatOpenAI` works by only changing `base_url`.

**Reliability:** created once (`@lru_cache`), `timeout=60`, `max_retries=2`. Any failure becomes `LLMError` → HTTP 502, and nothing is saved.

**Likely interview questions**

- *Can the model still hallucinate?* Yes. Prompts reduce it but can't guarantee it. Mitigations: low temperature, citations the user can check, and storing sources for auditing. Stronger options: a second "is every sentence supported?" check, or a stronger model.
- *Prompt injection?* A document could contain "ignore previous instructions". The damage is limited here because the LLM has no tools and only produces text, and passages are clearly delimited as data. It is still a known limitation.

---

## 8. Django structure used here

| Piece | File | Role |
|---|---|---|
| Model | `models.py` | Database table as a Python class. `FileField` stores the path; the file lives in `MEDIA_ROOT`. |
| Migration | `migrations/0001_initial.py` | Versioned DB schema change, generated by `makemigrations`. |
| Admin | `admin.py` | Auto-generated CRUD UI. `ModelAdmin` options control list columns, search, read-only fields. |
| Form | `forms.py` | Validation + saving for HTML forms. `clean_<field>()` validates one field; `clean()` the whole form. |
| Signals | `signals.py` | Hooks on model events (`post_delete`…). Used to delete files from disk. |
| Management command | `management/commands/` | `python manage.py load_sample_data`. |
| Settings | `core/settings.py` | Configuration, read from environment variables. |

**Service layer (`services.py`):** Django doesn't prescribe one, but it's a common pattern. Views and admin only translate HTTP/forms ↔ Python, and the real logic lives in plain functions that both call. This avoids duplicated logic and keeps behaviour identical in admin and API.

**`transaction.on_commit`:** files are deleted only after the database change is committed. If the transaction rolls back, the file is still there and the row still points to it.

**`.only()`, `.defer()`, `annotate(Length(...))`:** load only the columns you need. The document list counts characters in SQL instead of loading every full text into Python.

**`auto_now` / `auto_now_add`:** `updated_at` changes on every save, which is what lets the index detect edits with one cheap query.

---

## 9. Django REST Framework

| Concept | Here |
|---|---|
| **Serializer** | Converts model ↔ JSON and validates input (`serializers.py`). `validate_file()` runs our docx checks. |
| **ViewSet + Router** | `ModelViewSet` gives list/create/retrieve/update/destroy in one class; the router generates the URLs. |
| **APIView** | For non-CRUD actions such as `POST /ask/`. |
| **Authentication** | *Who are you?* Session (browser) or Basic (username:password header). |
| **Permission** | *May you do this?* `IsAuthenticated` by default; `AllowAny` for health. |
| **Throttling** | Rate limits. `ScopedRateThrottle` with scope `ask` = 20/min. |
| **Pagination** | `PageNumberPagination`, 20 per page. |
| **drf-spectacular** | Reads the serializers and views and generates an OpenAPI schema, plus Swagger/ReDoc pages. `@extend_schema` adds summaries and error responses. |

**HTTP status codes used:** 200 OK, 201 Created, 204 No Content (delete), 400 invalid input, 403 not authenticated, 404 not found, 409 conflict (no documents), 429 throttled, 502 upstream (LLM) failure.

---

## 10. Concurrency and the in-memory index

- A web server handles several requests at once, with **processes** (gunicorn workers) and/or **threads**.
- Each **process** has its own memory, so N workers means N copies of the model (~300 MB with PyTorch) and N indexes, each rebuilt separately. That's why we use **1 worker × 4 threads**.
- Python's **GIL** lets only one thread run Python code at a time. But a thread waiting for the network (the LLM call, 2–5 s) releases it, so threads are effective for this I/O-bound workload.
- **Race condition:** two threads notice "documents changed" at the same time and both rebuild. The `threading.Lock` in `DocumentIndex.get()` serialises the check-and-rebuild.
- **Immutable index + swap:** a new `HybridIndex` is fully built before replacing the old one, so a thread never searches a half-built index.

---

## 11. Docker

- **Image** = a filesystem snapshot with Python, dependencies and code. **Container** = a running image.
- **Layers and caching:** each Dockerfile instruction is a layer. Copying `requirements.txt` and installing *before* copying the code means code changes don't re-install dependencies.
- **CPU-only PyTorch:** the default Linux wheel bundles CUDA GPU libraries (~2 GB) we'd never use.
- **Model baked into the image** plus `HF_HUB_OFFLINE=1`: the container starts without internet access to HuggingFace and behaves the same every time.
- **Volume** (`app-data`): data that survives `docker compose down` and rebuilds (SQLite DB + uploads).
- **Entrypoint vs CMD:** the entrypoint script does setup (migrate, create admin, sample data), then `exec "$@"` runs the CMD (gunicorn) as the main process, so it receives stop signals correctly.
- **Non-root user:** if the app were compromised, the attacker wouldn't be root inside the container.
- **Static files:** with `DEBUG=False` Django doesn't serve CSS/JS. `collectstatic` gathers them at build time and `whitenoise` serves them.
- **CRLF trap:** on Windows, Git may convert `\n` to `\r\n`. `sh` in Linux then fails with confusing errors. `.gitattributes` forces LF for `.sh` files.

---

## 12. Testing approach

- **Unit tests** for the pure pipeline (`test_extract`, `test_chunking`, `test_index`) use `SimpleTestCase` (no database, fast). `.docx` files are built in memory with python-docx, so each test shows exactly the structure it checks.
- **Integration tests** (`test_api`) go through HTTP with DRF's `APIClient` and Django's test client for the admin, using a real test database and a temporary `MEDIA_ROOT`.
- **Fakes, not network:** `DeterministicFakeEmbedding` (the same text always gives the same vector) and `FakeListChatModel` (returns canned answers). Tests are fast, free, deterministic and need no API key. The real LLM was checked separately by hand.
- **`captureOnCommitCallbacks(execute=True)`:** Django tests run inside a transaction that's rolled back, so `on_commit` callbacks never fire unless captured. That's needed to test file deletion.
- **A flaky test found a real bug:** the duplicate-upload test failed only sometimes. Cause: python-docx writes the current time into the file, so two "identical" files made a second apart had different bytes and different hashes. Fix: hash the extracted *text*. **Flaky tests are signals, not noise.**

---

## 13. Configuration and security basics

- **12-factor config:** settings come from environment variables, so the same code runs in dev, Docker and production; only the environment changes. `.env` is local only and git-ignored. `.env.example` documents the variables.
- **`SECRET_KEY`** signs sessions and CSRF tokens. If it leaks, sessions can be forged. The old one was committed to git, so it must never be used in production (the new code reads it from the environment).
- **`DEBUG=True` in production** leaks stack traces and settings. Here it defaults to off and Docker forces it off.
- **`ALLOWED_HOSTS`** protects against Host-header attacks.
- **Uploaded files are private:** served only to logged-in staff.
- **Validate uploads:** extension, size, parseability, duplicates. Never trust the client.
