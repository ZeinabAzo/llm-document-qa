import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from rag_app.models import Document, QAHistory

from .helpers import fake_rag, handbook_docx, upload

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT, OPENROUTER_MODEL="test/model")
class APITestBase(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw")
        self.client.force_authenticate(self.user)

    def upload_document(self, name="handbook.docx", content=None, **extra):
        return self.client.post(
            reverse("document-list"),
            {"file": upload(name, content or handbook_docx()), **extra},
            format="multipart",
        )


class AuthTests(APITestBase):
    def test_api_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("document-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("ask"), {"question": "x"}).status_code, 403)

    def test_health_is_public(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok"})

    def test_api_docs_are_public(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("schema")).status_code, 200)
        self.assertEqual(self.client.get(reverse("swagger-ui")).status_code, 200)

    def test_basic_auth_works(self):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION="Basic YWxpY2U6cHc=")  # alice:pw
        self.assertEqual(self.client.get(reverse("document-list")).status_code, 200)


class DocumentAPITests(APITestBase):
    def test_upload_extracts_text_and_defaults_title(self):
        response = self.upload_document()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["title"], "handbook.docx")
        self.assertGreater(response.data["text_length"], 0)
        document = Document.objects.get()
        self.assertIn("## 1.1 Vacation", document.extracted_text)
        self.assertEqual(len(document.content_hash), 64)

    def test_upload_with_custom_title(self):
        response = self.upload_document(title="Employee Handbook")
        self.assertEqual(response.data["title"], "Employee Handbook")

    def test_duplicate_upload_is_rejected(self):
        self.upload_document()
        response = self.upload_document(name="copy.docx")
        self.assertEqual(response.status_code, 400)
        self.assertIn("already uploaded", response.data["file"][0])
        self.assertEqual(Document.objects.count(), 1)

    def test_non_docx_extension_is_rejected(self):
        response = self.upload_document(name="notes.pdf")
        self.assertEqual(response.status_code, 400)

    def test_corrupt_docx_is_rejected_and_nothing_saved(self):
        response = self.upload_document(content=b"not really a docx")
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid .docx", response.data["file"][0])
        self.assertEqual(Document.objects.count(), 0)

    def test_list_omits_text_and_detail_includes_it(self):
        doc_id = self.upload_document().data["id"]
        listing = self.client.get(reverse("document-list")).data
        self.assertEqual(listing["count"], 1)
        self.assertNotIn("extracted_text", listing["results"][0])
        detail = self.client.get(reverse("document-detail", args=[doc_id])).data
        self.assertIn("22 days", detail["extracted_text"])

    def test_rename_keeps_text(self):
        doc_id = self.upload_document().data["id"]
        response = self.client.patch(
            reverse("document-detail", args=[doc_id]), {"title": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        document = Document.objects.get()
        self.assertEqual(document.title, "Renamed")
        self.assertIn("22 days", document.extracted_text)

    def test_replacing_file_re_extracts_text_and_deletes_old_file(self):
        doc_id = self.upload_document().data["id"]
        old_path = Path(Document.objects.get().file.path)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                reverse("document-detail", args=[doc_id]),
                {"file": upload("v2.docx", handbook_docx(extra="Version two."))},
                format="multipart",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Version two.", Document.objects.get().extracted_text)
        self.assertFalse(old_path.exists())

    def test_delete_removes_row_and_file(self):
        doc_id = self.upload_document().data["id"]
        path = Path(Document.objects.get().file.path)
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(reverse("document-detail", args=[doc_id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Document.objects.exists())
        self.assertFalse(path.exists())


class AskAPITests(APITestBase):
    def ask(self, **data):
        return self.client.post(reverse("ask"), data, format="json")

    def test_ask_returns_answer_with_sources_and_saves_history(self):
        self.upload_document()
        with fake_rag(answers=["You get 22 days of PTO [1]."]):
            response = self.ask(question="  How many vacation days?  ", top_k=2)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["answer"], "You get 22 days of PTO [1].")
        self.assertEqual(response.data["question"], "How many vacation days?")
        self.assertEqual(response.data["model_name"], "test/model")
        self.assertEqual(len(response.data["sources"]), 2)
        self.assertEqual(response.data["sources"][0]["number"], 1)
        self.assertEqual(response.data["sources"][0]["document_title"], "handbook.docx")
        self.assertEqual(QAHistory.objects.get().answer, "You get 22 days of PTO [1].")

    def test_keyword_question_retrieves_the_right_section(self):
        self.upload_document()
        with fake_rag():
            response = self.ask(question="security-sos@example.com", top_k=1)
        self.assertEqual(response.data["sources"][0]["section"], "2. Security")

    def test_index_picks_up_new_documents(self):
        self.upload_document()
        with fake_rag():
            self.ask(question="first")
            self.upload_document(name="b.docx", content=handbook_docx(extra="Zebra policy."))
            response = self.ask(question="zebra", top_k=1)
        self.assertIn("Zebra", response.data["sources"][0]["excerpt"])

    def test_ask_without_documents_returns_409(self):
        with fake_rag():
            response = self.ask(question="Anything?")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(QAHistory.objects.exists())

    def test_llm_failure_returns_502_and_saves_nothing(self):
        self.upload_document()
        with fake_rag(llm_error=TimeoutError("timed out")):
            response = self.ask(question="How many vacation days?")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(QAHistory.objects.exists())

    def test_invalid_input(self):
        self.assertEqual(self.ask(question="   ").status_code, 400)
        self.assertEqual(self.ask(question="ok", top_k=0).status_code, 400)

    def test_history_list_and_detail(self):
        self.upload_document()
        with fake_rag():
            entry_id = self.ask(question="Q1").data["id"]
        listing = self.client.get(reverse("history-list")).data
        self.assertEqual(listing["results"][0]["question"], "Q1")
        detail = self.client.get(reverse("history-detail", args=[entry_id]))
        self.assertEqual(detail.status_code, 200)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin", password="pw")
        self.client.force_login(self.admin)

    def test_admin_pages_render(self):
        call_command("load_sample_data", stdout=open(Path(MEDIA_ROOT) / "out.txt", "w"))
        document = Document.objects.get()
        for url in [
            reverse("admin:rag_app_document_changelist"),
            reverse("admin:rag_app_document_change", args=[document.pk]),
            reverse("admin:rag_app_qahistory_add"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_upload_rejects_duplicate(self):
        url = reverse("admin:rag_app_document_add")
        self.client.post(url, {"title": "", "file": upload("a.docx", handbook_docx())})
        response = self.client.post(url, {"title": "", "file": upload("b.docx", handbook_docx())})
        self.assertContains(response, "already uploaded")
        self.assertEqual(Document.objects.count(), 1)

    def test_ask_question_from_admin(self):
        self.client.post(
            reverse("admin:rag_app_document_add"),
            {"title": "", "file": upload("a.docx", handbook_docx())},
        )
        with fake_rag(answers=["22 days [1]."]):
            response = self.client.post(
                reverse("admin:rag_app_qahistory_add"), {"question": "Vacation days?"}
            )
        self.assertEqual(response.status_code, 302)
        entry = QAHistory.objects.get()
        self.assertEqual(entry.answer, "22 days [1].")
        detail = self.client.get(reverse("admin:rag_app_qahistory_change", args=[entry.pk]))
        self.assertContains(detail, "22 days [1].")

    def test_admin_ask_shows_error_when_llm_fails(self):
        self.client.post(
            reverse("admin:rag_app_document_add"),
            {"title": "", "file": upload("a.docx", handbook_docx())},
        )
        with fake_rag(llm_error=RuntimeError("boom")):
            response = self.client.post(
                reverse("admin:rag_app_qahistory_add"), {"question": "Vacation days?"}
            )
        self.assertContains(response, "unavailable")
        self.assertFalse(QAHistory.objects.exists())
