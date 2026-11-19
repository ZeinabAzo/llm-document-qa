from rest_framework import serializers

from . import services
from .models import Document, QAHistory


class DocumentSerializer(serializers.ModelSerializer):
    """Used for list/create/update. Omits the (possibly huge) extracted text."""

    text_length = serializers.SerializerMethodField(help_text="Characters of extracted text.")

    class Meta:
        model = Document
        fields = ["id", "title", "file", "content_hash", "text_length", "created_at", "updated_at"]
        read_only_fields = ["content_hash", "created_at", "updated_at"]
        extra_kwargs = {"title": {"required": False}}

    def get_text_length(self, obj: Document) -> int:
        # The list view annotates this in SQL; fall back to len() for single objects.
        annotated = getattr(obj, "text_length", None)
        return annotated if annotated is not None else len(obj.extracted_text)

    def validate_file(self, file):
        exclude_pk = self.instance.pk if self.instance else None
        self._parsed = services.parse_docx_upload(file, exclude_pk=exclude_pk)
        return file

    def save(self, **kwargs):
        parsed = getattr(self, "_parsed", None)
        if parsed:
            kwargs.update(extracted_text=parsed.text, content_hash=parsed.content_hash)
        return super().save(**kwargs)


class DocumentDetailSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["extracted_text"]


class SourceSerializer(serializers.Serializer):
    """One retrieved passage. `number` matches the [n] citations in the answer."""

    number = serializers.IntegerField()
    document_id = serializers.IntegerField()
    document_title = serializers.CharField()
    section = serializers.CharField(allow_blank=True)
    excerpt = serializers.CharField()
    score = serializers.FloatField(help_text="Reciprocal Rank Fusion score (higher is better).")
    vector_rank = serializers.IntegerField(allow_null=True)
    keyword_rank = serializers.IntegerField(allow_null=True)


class QAHistorySerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = QAHistory
        fields = ["id", "question", "answer", "sources", "model_name", "latency_ms", "created_at"]
        read_only_fields = fields


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, trim_whitespace=True)
    top_k = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=20,
        help_text="How many passages to retrieve (default 5).",
    )
