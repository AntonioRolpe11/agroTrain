from django.urls import path

from . import views

urlpatterns = [
    path("validate-features", views.validate_features, name="validate-features"),
    path("flamapy/satisfiable", views.satisfiable, name="satisfiable"),
    path("flamapy/configurations-number", views.configurations_number, name="configurations-number"),
    path("flamapy/dead-features", views.dead_features, name="dead-features"),
    path("model", views.feature_model, name="feature-model"),
    path("configuraciones/", views.configuracion_list_create, name="configuracion-list-create"),
    path("configuraciones/<int:pk>/", views.configuracion_detail, name="configuracion-detail"),
]

uvl_urlpatterns = [
    path("versions/", views.uvl_version_list, name="uvl-version-list"),
    path("versions/validate/", views.uvl_version_validate, name="uvl-version-validate"),
    path("versions/create/", views.uvl_version_create, name="uvl-version-create"),
    path("versions/<int:pk>/", views.uvl_version_detail_or_delete, name="uvl-version-detail"),
    path("versions/<int:pk>/preview-activation/", views.uvl_version_preview_activation, name="uvl-preview-activation"),
    path("versions/<int:pk>/activate/", views.uvl_version_activate, name="uvl-activate"),
]
