from django.db.models.functions import Length
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .models import Document, QAHistory
from .serializers import (
    AskSerializer,
    DocumentDetailSerializer,
    DocumentSerializer,
    QAHistorySerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List documents"),
    create=extend_schema(summary="Upload a .docx document"),
    retrieve=extend_schema(summary="Get a document, including its extracted text"),
    update=extend_schema(summary="Replace a document (title and file)"),
    partial_update=extend_schema(summary="Rename a document or replace its file"),
    destroy=extend_schema(summary="Delete a document and its file"),
)
class DocumentViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = Document.objects.all()
        if self.action == "list":
            # Count characters in SQL instead of loading every full text.
            queryset = queryset.defer("extracted_text").annotate(
                text_length=Length("extracted_text")
            )
        return queryset

    def get_serializer_class(self):
        return DocumentDetailSerializer if self.action == "retrieve" else DocumentSerializer


@extend_schema_view(
    list=extend_schema(summary="List previous questions and answers"),
    retrieve=extend_schema(summary="Get one question and answer"),
)
class QAHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = QAHistory.objects.all()
    serializer_class = QAHistorySerializer


class AskView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ask"

    @extend_schema(
        summary="Ask a question about the uploaded documents",
        request=AskSerializer,
        responses={
            201: QAHistorySerializer,
            400: OpenApiResponse(description="Invalid input."),
            409: OpenApiResponse(description="No documents have been uploaded yet."),
            502: OpenApiResponse(description="The LLM provider failed or timed out."),
        },
    )
    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry = services.ask(**serializer.validated_data)
        except services.NoDocumentsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except services.LLMError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(QAHistorySerializer(entry).data, status=status.HTTP_201_CREATED)


class HealthView(APIView):
    """Liveness check for Docker / load balancers. Does not touch the LLM."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(summary="Health check", responses={200: OpenApiResponse(description="OK")})
    def get(self, request):
        return Response({"status": "ok"})
