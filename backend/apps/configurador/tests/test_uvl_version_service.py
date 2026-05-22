from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.models import Configuracion, UVLVersion
from apps.configurador.services.flamapy_service import FlamapyService
from apps.configurador.services.uvl_version_service import (
    _sha256,
    activate_version,
    create_version,
    preview_activation,
    seed_initial_version,
    validate_uvl_text,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_min.uvl"


@pytest.fixture
def versions_path(tmp_path, settings):
    settings.UVL_VERSIONS_PATH = tmp_path
    return tmp_path


def _valid_tree() -> dict:
    """Return the serialized fixture tree (with constraints stripped) for create_version."""
    FlamapyService.warm_up(FIXTURE_PATH)
    return {**FlamapyService.to_dict()}


def _valid_constraints_text() -> str:
    return (
        "Dendrometro => DatoMCD | DatoTB\n"
        "MCD => DatoMCD\n"
        "TasaBuenos => DatoTB\n"
        "RiegoControl => TemperaturaAire\n"
    )


class TestValidateUvlText:
    def test_valid_uvl_returns_no_errors(self):
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        errors = validate_uvl_text(text)
        assert errors == []

    def test_syntax_error_caught(self):
        errors = validate_uvl_text("not valid uvl at all")
        assert errors
        assert any("UVL" in err or "BDD" in err for err in errors)

    def test_missing_required_nodes_reported(self, tmp_path):
        bad = """namespace x
features
\tRoot
\t\tmandatory
\t\t\tA { wizard_step 'parcel' }
\t\t\tB { wizard_step 'sensors' }
"""
        errors = validate_uvl_text(bad)
        assert errors
        assert any("Nodos raíz requeridos" in e or "wizard_step" in e for e in errors)


@pytest.mark.django_db
class TestSeedInitialVersion:
    def test_creates_initial_version_when_db_empty(self, versions_path):
        UVLVersion.objects.all().delete()
        seed_initial_version(FIXTURE_PATH)
        assert UVLVersion.objects.filter(is_active=True).count() == 1

    def test_does_nothing_when_versions_exist(self, versions_path):
        seed_initial_version(FIXTURE_PATH)
        initial = UVLVersion.objects.count()
        seed_initial_version(FIXTURE_PATH)
        assert UVLVersion.objects.count() == initial


@pytest.mark.django_db
class TestCreateVersion:
    def test_creates_version_when_valid(self, versions_path, admin_user):
        tree = _valid_tree()
        version, errors = create_version(
            name="v2",
            description="test",
            tree=tree,
            constraints_text=_valid_constraints_text(),
            author=admin_user,
        )
        assert errors == []
        assert version is not None
        assert version.name == "v2"
        assert version.is_valid is True
        # file is persisted in versions_path
        assert (versions_path / version.file_path).exists()

    def test_rejects_duplicate_hash(self, versions_path, admin_user):
        tree = _valid_tree()
        ct = _valid_constraints_text()
        create_version("v1", "", tree, ct, author=admin_user)
        second, errors = create_version("v1-dup", "", tree, ct, author=admin_user)
        assert errors and "idéntica" in errors[0]

    def test_returns_errors_when_invalid_tree(self, versions_path, admin_user):
        bad_tree = {"name": "Lonely", "relations": []}
        version, errors = create_version(
            name="bad", description="", tree=bad_tree, constraints_text="", author=admin_user
        )
        assert version is None
        assert errors


@pytest.mark.django_db
class TestPreviewActivation:
    def _make_version(self, versions_path, admin_user):
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        fname = "preview.uvl"
        (versions_path / fname).write_text(text, encoding="utf-8")
        return UVLVersion.objects.create(
            name="prev", description="", file_path=fname,
            file_hash=_sha256(text) + "preview",  # unique hash
            author=admin_user, is_active=False, is_valid=True, validation_errors=[],
        )

    def test_no_affected_when_db_empty(self, versions_path, admin_user):
        version = self._make_version(versions_path, admin_user)
        report = preview_activation(version.pk)
        assert report["total"] == 0
        assert report["affected"] == []

    def test_detects_config_with_unknown_features(self, versions_path, admin_user):
        version = self._make_version(versions_path, admin_user)
        Configuracion.objects.create(
            user=admin_user, nombre="legacy",
            features=["FeatureThatDoesNotExist"], geo={},
        )
        report = preview_activation(version.pk)
        assert report["total"] == 1
        assert len(report["affected"]) == 1
        assert "FeatureThatDoesNotExist" in report["affected"][0]["reason"]


@pytest.mark.django_db
class TestActivateVersion:
    def _make_version(self, versions_path, admin_user, name="v"):
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        fname = f"{name}.uvl"
        (versions_path / fname).write_text(text, encoding="utf-8")
        return UVLVersion.objects.create(
            name=name, description="", file_path=fname,
            file_hash=_sha256(text) + name,
            author=admin_user, is_active=False, is_valid=True, validation_errors=[],
        )

    def test_activates_and_warms_flamapy(self, versions_path, admin_user):
        version = self._make_version(versions_path, admin_user)
        success, error, _ = activate_version(version.pk, confirm_incompatible=False)
        assert success is True
        version.refresh_from_db()
        assert version.is_active is True

    def test_blocks_invalid_version(self, versions_path, admin_user):
        version = self._make_version(versions_path, admin_user)
        version.is_valid = False
        version.save()
        ok, error, _ = activate_version(version.pk)
        assert ok is False
        assert "validación" in error or "valid" in error.lower()

    def test_requires_confirmation_for_incompatible_configs(self, versions_path, admin_user):
        version = self._make_version(versions_path, admin_user, name="other")
        Configuracion.objects.create(
            user=admin_user, nombre="oops", features=["NonExistent"], geo={},
        )
        ok, error, report = activate_version(version.pk, confirm_incompatible=False)
        assert ok is False
        assert report is not None
        assert report["affected"]
