"""El estado de modelos y migraciones debe estar sincronizado.

`makemigrations --check --dry-run` sale con código no-cero si algún cambio de
modelo carece de migración. Barato y atrapa el drift modelo↔migración antes de
que rompa el arranque en otro entorno.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_missing_migrations():
    out = StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
    except SystemExit as exc:  # --check aborta con status no-cero si faltan migraciones
        if exc.code:
            raise AssertionError(
                "Hay cambios de modelo sin migración. Ejecuta `python manage.py makemigrations`.\n"
                + out.getvalue()
            ) from exc
