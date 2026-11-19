from pathlib import Path

from django.core.validators import FileExtensionValidator
from django.db import models


class Document(models.Model):
    """An uploaded .docx file and the text extracted from it.

    Text is extracted once, at upload time (see `services.parse_docx_upload`), so a
    Document row always holds valid, searchable text. Invalid files are rejected
    before anything is saved.
    """

    title = models.CharField(
        max_length=255, blank=True, help_text="Defaults to the file name."
    )
    file = models.FileField(
        upload_to="documents/",
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
    )
    extracted_text = models.TextField(
        editable=False, help_text="Full document text as Markdown (headings, lists, tables)."
    )
    content_hash = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="SHA-256 of the extracted text. Prevents the same document being indexed twice.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.title and self.file:
            self.title = Path(self.file.name).name
        super().save(*args, **kwargs)


class QAHistory(models.Model):
    """One answered question, with the passages the answer was based on."""

    question = models.TextField()
    answer = models.TextField()
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Retrieved passages: document id/title, section, excerpt, score.",
    )
    model_name = models.CharField(max_length=200, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Q&A history entry"
        verbose_name_plural = "Q&A history"

    def __str__(self) -> str:
        return self.question[:80]
