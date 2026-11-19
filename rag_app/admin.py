from django.contrib import admin
from django.db.models.functions import Length
from django.template.defaultfilters import truncatechars
from django.utils.html import format_html, format_html_join

from .forms import AskQuestionForm, DocumentAdminForm
from .models import Document, QAHistory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ("title", "file", "text_length", "created_at", "updated_at")
    search_fields = ("title", "extracted_text")
    readonly_fields = ("content_hash", "created_at", "updated_at", "text_preview")
    fieldsets = (
        (None, {"fields": ("title", "file")}),
        ("Extracted content", {"fields": ("text_preview", "content_hash", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_text_length=Length("extracted_text"))

    @admin.display(description="Characters", ordering="_text_length")
    def text_length(self, obj: Document) -> int:
        return obj._text_length

    @admin.display(description="Extracted text (Markdown)")
    def text_preview(self, obj: Document) -> str:
        if not obj.extracted_text:
            return "-"
        return format_html(
            '<pre style="white-space: pre-wrap; max-height: 32rem; overflow: auto;">{}</pre>',
            obj.extracted_text,
        )


@admin.register(QAHistory)
class QAHistoryAdmin(admin.ModelAdmin):
    form = AskQuestionForm
    list_display = ("short_question", "short_answer", "model_name", "latency_ms", "created_at")
    search_fields = ("question", "answer")
    list_filter = ("created_at", "model_name")
    readonly_fields = ("answer", "sources_display", "model_name", "latency_ms", "created_at")

    def get_fields(self, request, obj=None):
        if obj is None:  # "Ask a question" page
            return ["question"]
        return ["question", "answer", "sources_display", "model_name", "latency_ms", "created_at"]

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # history is a record of what happened; view or delete only

    @admin.display(description="Question")
    def short_question(self, obj: QAHistory) -> str:
        return truncatechars(obj.question, 80)

    @admin.display(description="Answer")
    def short_answer(self, obj: QAHistory) -> str:
        return truncatechars(obj.answer, 120)

    @admin.display(description="Sources")
    def sources_display(self, obj: QAHistory) -> str:
        if not obj.sources:
            return "-"
        return format_html_join(
            "",
            '<div style="margin-bottom: 1em;"><strong>[{}] {}</strong> (score {})'
            '<pre style="white-space: pre-wrap;">{}</pre></div>',
            (
                (s["number"], s["document_title"], s["score"], s["excerpt"])
                for s in obj.sources
            ),
        )
