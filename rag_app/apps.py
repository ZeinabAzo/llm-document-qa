from django.apps import AppConfig


class RagAppConfig(AppConfig):
    name = "rag_app"
    verbose_name = "Document QA"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (registers signal handlers)
