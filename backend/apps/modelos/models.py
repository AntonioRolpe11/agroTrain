from __future__ import annotations

from django.conf import settings
from django.db import models


class ModeloGuardado(models.Model):
    model_id = models.CharField(max_length=36, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modelos",
    )
    algorithm = models.CharField(max_length=50)
    crop = models.CharField(max_length=100)
    features = models.JSONField(default=list)
    geo = models.JSONField(default=dict)
    targets = models.JSONField()
    input_features = models.JSONField()
    all_cols = models.JSONField(default=list)
    metrics = models.JSONField()
    warnings = models.JSONField(default=list)
    n_samples = models.IntegerField(default=0)
    n_train = models.IntegerField(default=0)
    n_val = models.IntegerField(default=0)
    window_size = models.IntegerField(default=0)
    imported = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.model_id[:8]} {self.algorithm}/{self.crop}"


class PrediccionModelo(models.Model):
    model = models.ForeignKey(
        ModeloGuardado,
        on_delete=models.CASCADE,
        related_name="predicciones",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="predicciones_modelos",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    predicted_for_date = models.DateField()
    predictions = models.JSONField()
    input_row_count = models.IntegerField(default=0)
    warnings = models.JSONField(default=list)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return f"{self.model.model_id[:8]} @ {self.generated_at:%Y-%m-%d %H:%M}"
