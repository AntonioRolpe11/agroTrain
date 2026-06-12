"""
Guardas de los acoplamientos UVL ↔ código hardcodeado.

El sistema deriva (casi) todo del UVL, pero quedan tres puntos de acoplamiento
manual que, si se desincronizan, fallan en runtime sin que ningún test los detecte:

1. Un `required_inputs` de un hyperprofile debe estar respaldado por una constraint
   del UVL que obligue a seleccionar el sensor correspondiente. CLAUDE.md lo marca
   como riesgo de fallo silencioso: el configurador no lee hyperprofiles, así que
   sin la constraint el wizard deja proseguir sin el sensor y el entrenamiento revienta.
2. Todo hyperprofile referenciado en el UVL debe existir en el registry.
3. Todo índice de telemetría con `csv_col` debe tener fórmula de banda GEE.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.configurador.services.flamapy_service import FlamapyService
from apps.modelos.services.hyperprofile_registry import HYPERPROFILE_REGISTRY, get_hyperprofile

_BACKEND_DIR = Path(__file__).resolve().parents[3]
ACTIVE_UVL = _BACKEND_DIR / "uvl_versions" / "v2_olivos_tratamientos.uvl"
TEST_MIN_UVL = _BACKEND_DIR / "apps" / "configurador" / "tests" / "fixtures" / "test_min.uvl"


@pytest.fixture
def active_uvl():
    FlamapyService.warm_up(ACTIVE_UVL)
    yield FlamapyService
    if TEST_MIN_UVL.exists():
        FlamapyService.warm_up(TEST_MIN_UVL)


def _sat_with_pins(service: FlamapyService, base_uvl: str, pins: list[str]) -> bool:
    """Satisfacibilidad del modelo con features fijadas (`name` = True, `!name` = False)."""
    constrained = base_uvl.rstrip() + "\n" + "\n".join(f"\t{p}" for p in pins) + "\n"
    return service.satisfiable(constrained)


def _reverse_csv_map() -> dict[str, str]:
    """columna CSV -> feature-sensor que la declara (bajo ParametrosEntrada)."""
    mapping: dict[str, str] = {}
    for feat in FlamapyService.get_subtree_feature_names("ParametrosEntrada"):
        for col in FlamapyService.get_csv_columns(feat):
            mapping.setdefault(col, feat)
    return mapping


def _treatments() -> list[str]:
    return [t for t in FlamapyService.get_subtree_feature_names("Tratamiento") if t != "Tratamiento"]


class TestHyperprofileConstraintMirroring:
    def test_required_inputs_are_enforced_by_constraints(self, active_uvl):
        service = FlamapyService(ACTIVE_UVL)
        base = ACTIVE_UVL.read_text(encoding="utf-8")
        col_to_feature = _reverse_csv_map()
        targets = FlamapyService.get_subtree_feature_names("VariableObjetivo")

        checked = 0
        for treatment in _treatments():
            for target in targets:
                hp_name = FlamapyService.get_treatment_target_profile(treatment, target).get("hyperprofile")
                if not hp_name:
                    continue
                for col in get_hyperprofile(hp_name).get("required_inputs", []):
                    sensor = col_to_feature.get(col)
                    assert sensor is not None, (
                        f"required_input {col!r} de {hp_name!r} no mapea a ningún sensor del UVL."
                    )
                    # Elegir tratamiento+objetivo excluyendo el sensor debe ser imposible.
                    sat = _sat_with_pins(service, base, [treatment, target, f"!{sensor}"])
                    assert sat is False, (
                        f"{treatment}+{target} usa el hyperprofile {hp_name!r} que exige la columna "
                        f"{col!r} (sensor {sensor!r}), pero el UVL permite seleccionarlo sin ese "
                        f"sensor. Falta una constraint del tipo `{target} => {sensor}`."
                    )
                    checked += 1
        # Evita que un rename de atributos deje la prueba comprobando nada en silencio.
        assert checked > 0, "Ningún hyperprofile con required_inputs llegó a verificarse."


class TestRegistryIntegrity:
    def test_every_uvl_hyperprofile_exists_in_registry(self, active_uvl):
        targets = FlamapyService.get_subtree_feature_names("VariableObjetivo")
        referenced = {
            hp
            for treatment in _treatments()
            for target in targets
            if (hp := FlamapyService.get_treatment_target_profile(treatment, target).get("hyperprofile"))
        }
        assert referenced, "El UVL no referencia ningún hyperprofile."
        missing = referenced - set(HYPERPROFILE_REGISTRY)
        assert not missing, f"Hyperprofiles referenciados en el UVL pero ausentes del registry: {missing}"


class TestTelemetryIndexFormulaCoupling:
    """Cada índice de DatosTelemetria con csv_col debe tener fórmula de banda GEE.
    `ee` está stubbeado en conftest, así que esto ejercita la cadena elif real sin satélite."""

    def test_each_telemetry_index_has_a_formula(self, active_uvl):
        from apps.telemetria.services.telemetry_service import TelemetryService, TelemetryServiceError

        indices = [
            f
            for f in FlamapyService.get_subtree_feature_names("DatosTelemetria")
            if FlamapyService.get_csv_columns(f)
        ]
        assert indices, "El UVL no declara índices de telemetría con csv_col."

        for index in indices:
            try:
                TelemetryService._add_requested_indices(MagicMock(name="image"), [index])
            except TelemetryServiceError as exc:
                pytest.fail(
                    f"El índice {index!r} declarado en el UVL no tiene fórmula GEE en "
                    f"telemetry_service.py: {exc}"
                )
