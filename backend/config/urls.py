from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.configurador.urls import uvl_urlpatterns


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health", health, name="health"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/configurator/", include("apps.configurador.urls")),
    path("api/v1/uvl/", include((uvl_urlpatterns, "uvl"))),
    path("api/v1/geo/", include("apps.geo.urls")),
    path("api/v1/telemetry/", include("apps.telemetria.urls")),
    path("api/v1/modelos/", include("apps.modelos.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
