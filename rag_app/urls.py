from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from .views import AskView, DocumentViewSet, HealthView, QAHistoryViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("history", QAHistoryViewSet, basename="history")

urlpatterns = [
    path("", include(router.urls)),
    path("ask/", AskView.as_view(), name="ask"),
    path("health/", HealthView.as_view(), name="health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
