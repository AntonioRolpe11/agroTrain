from __future__ import annotations

import logging
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ConfiguradorConfig(AppConfig):
    name = "apps.configurador"
    verbose_name = "Configurador de Sensores"

    def ready(self) -> None:
        from django.db.models.signals import post_migrate
        post_migrate.connect(_on_post_migrate, sender=self)

        from django.conf import settings as s
        from .services.flamapy_service import FlamapyService

        # Try to load from active DB version; fall back to default file.
        # DB may not exist yet (first migrate) — errors are caught silently.
        uvl_path, version_id = _resolve_active_uvl_path(Path(s.UVL_MODEL_PATH), Path(s.UVL_VERSIONS_PATH))
        try:
            FlamapyService.warm_up(uvl_path, version_id=version_id)
            logger.info("Flamapy BDD preconstruido desde %s", uvl_path)
        except Exception as exc:
            logger.warning("No se pudo preconstruir el BDD de Flamapy: %s", exc)


def _resolve_active_uvl_path(default_path: Path, versions_path: Path) -> tuple[Path, int | None]:
    try:
        from .models import UVLVersion
        active = UVLVersion.objects.filter(is_active=True).first()
        if active:
            return versions_path / active.file_path, active.pk
    except Exception:
        pass
    return default_path, None


def _on_post_migrate(sender, **kwargs):
    """Seed initial UVL version after migrations complete."""
    from django.conf import settings as s
    try:
        from .services.uvl_version_service import seed_initial_version
        seed_initial_version(Path(s.UVL_MODEL_PATH))
    except Exception as exc:
        logger.debug("No se pudo sembrar versión UVL inicial: %s", exc)
