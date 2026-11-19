from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from rag_app import services
from rag_app.models import Document

SAMPLE_DIR = Path(settings.BASE_DIR) / "sample_data"


class Command(BaseCommand):
    help = "Upload the .docx files from sample_data/ (skips ones already uploaded)."

    def handle(self, *args, **options):
        for path in sorted(SAMPLE_DIR.glob("*.docx")):
            upload = SimpleUploadedFile(path.name, path.read_bytes())
            try:
                parsed = services.parse_docx_upload(upload)
            except ValidationError as exc:
                self.stdout.write(f"Skipped {path.name}: {' '.join(exc.messages)}")
                continue
            document = Document(file=upload)
            services.apply_parsed_upload(document, parsed)
            document.save()
            self.stdout.write(self.style.SUCCESS(f"Loaded {path.name} (id {document.pk})"))
