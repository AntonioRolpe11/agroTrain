from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("train", views.train_model, name="modelos-train"),
    path("import", views.import_model, name="modelos-import"),
    path("", views.list_models, name="modelos-list"),
    path("<str:model_id>/status", views.get_status, name="modelos-status"),
    path("<str:model_id>/predict", views.predict_model, name="modelos-predict"),
    path("<str:model_id>/predictions", views.list_predictions, name="modelos-predictions"),
    path("<str:model_id>/predictions/<int:prediction_id>", views.delete_prediction, name="modelos-prediction-delete"),
    path("<str:model_id>/download", views.download_model, name="modelos-download"),
    path("<str:model_id>/", views.model_detail, name="modelos-detail"),
]
