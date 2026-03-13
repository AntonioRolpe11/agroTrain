from django.urls import path

from . import views

urlpatterns = [
    path("provincias", views.get_provincias, name="get-provincias"),
    path("municipios", views.get_municipios, name="get-municipios"),
    path("municipio-viewport", views.get_municipio_viewport, name="get-municipio-viewport"),
]
