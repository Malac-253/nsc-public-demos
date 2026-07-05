from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("party.urls")),
]

# Serve uploaded files from local disk when not using S3/cloud storage.
if settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
