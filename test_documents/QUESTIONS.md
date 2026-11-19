# Test documents and questions

Upload these four files (in the admin or with `POST /api/documents/`), then ask the questions below. All 28 were run end to end against the real pipeline (local embeddings, hybrid search, OpenRouter) and answered as listed. Wording may vary slightly from run to run, since an LLM writes the answer, but the facts and the fallback behaviour should not.

| File | What it contains | What it tests |
|---|---|---|
| `Aurora_Cloud_Hosting_Service_Guide.docx` | Hosting company guide | Real Word heading styles, a plans table with repeated `Yes \| Yes` values, a merged table row, bullet list |
| `Meridian_Clinic_Patient_Policy.docx` | Clinic policy | Fake bold numbered headings, a callout box, codes/emails/phone numbers, a directory table |
| `Lindqvist_Foundation_Board_Minutes.docx` | Meeting minutes | No headings at all, plain paragraphs and bullets |
| `../sample_data/NovaTech_..._Handbook_2026.docx` | IT handbook | The original sample (fake headings, tables, callout) |

All names, numbers and contact details in these files are fictional.

## Questions and expected answers

### Tables and merged cells (Aurora)

| # | Question | Expected answer |
|---|---|---|
| 1 | How much does the Pro plan cost per month? | EUR 79 |
| 2 | Which hosting plans include daily backups? | Business, Pro and Enterprise (not Starter) |
| 3 | Does the Pro plan include a dedicated IP? | Yes (a `Yes \| Yes` row: both values must survive extraction) |
| 4 | Do Aurora's prices include VAT? | No, they exclude VAT (21%). The answer is in a merged table row |
| 5 | What discount does annual prepayment give at Aurora? | 15% (same merged row) |
| 6 | What is the price of the Enterprise plan? | A custom quote. Not a fallback: the document does answer this |

### Lists, numbers and reasoning (Aurora)

| # | Question | Expected answer |
|---|---|---|
| 7 | How quickly does Aurora reply to a Business plan ticket? | Within 8 hours |
| 8 | What is the 24/7 support phone number and which plans get it? | +31 20 555 0142; Pro and Enterprise |
| 9 | If a Pro plan's uptime is 0.3% below the guarantee, how much service credit is due? | 15% (5% for each full 0.1%, cap 50%). Needs a small calculation |

### Exact identifiers and the callout box (Meridian)

| # | Question | Expected answer |
|---|---|---|
| 10 | Which form do I need to request my medical records and where do I send it? | FORM-HC-204, to records@meridianclinic.example. Good case for keyword (BM25) search |
| 11 | What should I bring to every visit to the clinic? | Photo ID and insurance card. Comes from the 1x1 callout box |
| 12 | What is the fee for missing an appointment without notice? | EUR 25 |
| 13 | What time does the clinic close on Friday? | 15:00 |
| 14 | When is the clinic open on Monday? | 07:30 to 19:00 |
| 15 | Which insurers does the clinic accept? | Allianz, AXA and Zorg Plus |
| 16 | Can a 14-year-old go to the clinic alone? | No, children under 16 must be accompanied. Needs inference from "under 16" |
| 17 | Who heads Cardiology and what is their extension? | Dr. Tomas Becker, 2204 (directory table) |

### No headings (Lindqvist minutes)

| # | Question | Expected answer |
|---|---|---|
| 18 | How much budget was approved for the website relaunch? | EUR 240,000 |
| 19 | What was the result of the vote on moving the office to Hamburg? | Rejected by 4 votes to 1 |
| 20 | What must the Treasurer deliver and by when? | Ravi Patel: the revised financial forecast by 27 March 2026 |
| 21 | When is the next board meeting? | 16 April 2026 at 10:00 |

### Several documents at once

| # | Question | Expected answer |
|---|---|---|
| 22 | Who is the CEO of Aurora and who is the CEO of NovaTech? | Lars Veldman; Elena Vance. Passages come from two documents |
| 23 | Who leads Project Meridian and when does it launch? | Devon Okafor, December 3, 2026. **Name trap:** "Meridian" is also the clinic's name; the answer must come from the NovaTech handbook |
| 24 | What is the mandatory 2FA application at NovaTech? | AuthKey |

### Traps: the document does not say (expect the fallback)

The answer must be exactly: *"I don't have enough information in the provided documents to answer this question."*

| # | Question | Why it is a trap |
|---|---|---|
| 25 | What is the capital of France? | General knowledge, not in any document |
| 26 | Who voted against moving the office to Hamburg? | The minutes give only the count (4 to 1), not names |
| 27 | Does Aurora offer a Windows hosting plan? | Plans are listed; Windows is never mentioned |
| 28 | What is Clara Dubois's job title? | She appears only in the apologies; no role is given |

## Other checks worth doing by hand

- Upload the same file twice: you should get a duplicate error, and nothing is added.
- Upload a `.pdf` or a renamed text file: rejected with a clear message.
- Delete a document, then ask about it: the answer must fall back. The index updates on its own.
- In the admin, open a saved answer and compare its citations `[n]` with the listed source passages.
