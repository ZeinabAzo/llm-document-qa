# How to use

Open a terminal in the project folder, then:

## 1. Ask questions

```powershell
venv\Scripts\activate
python manage.py ask
```

Type a question and press Enter. Press Enter on an empty line to quit.

- You don't say which document: all uploaded documents are searched.
- The first answer takes about 15 seconds, then about 3.
- No documents yet? Run `python manage.py load_sample_data`.
- Try the questions in [test_documents/QUESTIONS.md](test_documents/QUESTIONS.md).

## 2. Upload and manage documents

```powershell
python manage.py runserver
```

Open **http://127.0.0.1:8000/admin/** and log in.

- **Documents → Add**: upload a `.docx`.
- **Q&A history**: past answers and their sources. **Add** lets you ask from the browser.

No admin account yet? Run `python manage.py createsuperuser`.

## If something goes wrong

| You see | Do this |
|---|---|
| `'python' is not recognized` or `No module named django` | Run `venv\Scripts\activate` first |
| `No documents have been uploaded yet` | Upload one in the admin, or `python manage.py load_sample_data` |
| `The language model is unavailable` | The free model is busy. Wait a minute and retry |
| `I don't have enough information…` | The documents don't say. This is correct for off-topic questions |

---

The REST API, Docker and the other commands are in [README.md](README.md) and [docs/API.md](docs/API.md).
