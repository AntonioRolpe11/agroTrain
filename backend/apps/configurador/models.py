from __future__ import annotations

from django.conf import settings
from django.db import models


class UVLVersion(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file_path = models.CharField(max_length=500)  # relative to UVL_VERSIONS_PATH
    file_hash = models.CharField(max_length=64, unique=True)   # SHA-256 hex
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uvl_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        active = " [ACTIVA]" if self.is_active else ""
        return f"{self.name}{active}"


class Configuracion(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="configuraciones",
    )
    nombre = models.CharField(max_length=200)
    features = models.JSONField()
    geo = models.JSONField()
    uvl_version = models.ForeignKey(
        UVLVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuraciones",
    )
    is_obsolete = models.BooleanField(default=False)
    obsolete_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.user})"
