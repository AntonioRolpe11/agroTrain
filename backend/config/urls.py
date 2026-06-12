from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.permissions import IsAdminRole
from apps.configurador.urls import uvl_urlpatterns


def health(_request):
    return JsonResponse({"status": "ok"})

schema_view = (
    SpectacularAPIView.as_view()
    if settings.DEBUG
    else SpectacularAPIView.as_view(permission_classes=[IsAdminRole])
)
docs_view = (
    SpectacularSwaggerView.as_view(url_name="schema")
    if settings.DEBUG
    else SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[IsAdminRole])
)


urlpatterns = [
    path("health", health, name="health"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/configurator/", include("apps.configurador.urls")),
    path("api/v1/uvl/", include((uvl_urlpatterns, "uvl"))),
    path("api/v1/geo/", include("apps.geo.urls")),
    path("api/v1/telemetry/", include("apps.telemetria.urls")),
    path("api/v1/modelos/", include("apps.modelos.urls")),
    path("schema/", schema_view, name="schema"),
    path("docs/", docs_view, name="swagger-ui"),
]
