from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, path
from django.views.static import serve

admin.site.site_header = "LLM Document QA"
admin.site.site_title = "LLM Document QA"
admin.site.index_title = "Documents & questions"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("rag_app.urls")),
    # Uploaded documents are private, so they are served only to logged-in staff.
    # Fine at this scale; a real deployment would use a proper file server.
    path(
        f"{settings.MEDIA_URL.lstrip('/')}<path:path>",
        staff_member_required(serve),
        {"document_root": settings.MEDIA_ROOT},
    ),
]
