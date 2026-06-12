"""
Global pytest configuration for agroTrain backend.

Provides:
    - Session-scoped warm_up of FlamapyService using the active UVL fixture.
    - Common user / client factories (admin and tecnico) with JWT auth.
    - tmp_model_storage to isolate model artifacts per test.
    - Mocked Earth Engine module so GEE is never hit from tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ----- Mock earthengine-api BEFORE telemetry_service imports it ---------------
# Some tests import telemetry_service indirectly; we want a deterministic stub.
if "ee" not in sys.modules:
    sys.modules["ee"] = MagicMock(name="ee_stub")


# ----- Flamapy warm_up --------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _warm_flamapy():
    """Warm up the BDD once per test session using the active UVL fixture file."""
    from apps.configurador.services.flamapy_service import FlamapyService

    fixture = Path(__file__).parent / "apps" / "configurador" / "tests" / "fixtures" / "test_min.uvl"
    if fixture.exists():
        try:
            FlamapyService.warm_up(fixture)
        except Exception:
            # If warm_up fails (e.g. missing flamapy), tests that depend on it will skip/fail
            # individually with a clearer message.
            pass
    yield


# ----- User + auth client fixtures -------------------------------------------

@pytest.fixture
def admin_user(db):
    from apps.accounts.models import ROLE_ADMIN, CustomUser
    return CustomUser.objects.create_user(
        email="admin@test.local",
        password="admin1234",
        nombre="Admin Test",
        role=ROLE_ADMIN,
    )


@pytest.fixture
def tecnico_user(db):
    from apps.accounts.models import ROLE_TECNICO, CustomUser
    return CustomUser.objects.create_user(
        email="tecnico@test.local",
        password="tecnico1234",
        nombre="Tecnico Test",
        role=ROLE_TECNICO,
    )


@pytest.fixture
def admin_client(admin_user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(admin_user)
    return client


@pytest.fixture
def tecnico_client(tecnico_user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(tecnico_user)
    return client


@pytest.fixture
def anon_client():
    from rest_framework.test import APIClient
    return APIClient()


# ----- Model storage isolation ------------------------------------------------

@pytest.fixture
def tmp_model_storage(tmp_path, settings):
    """Point MODELS_STORAGE_PATH at a per-test temp directory."""
    storage = tmp_path / "model_storage"
    storage.mkdir()
    settings.MODELS_STORAGE_PATH = storage
    return storage
