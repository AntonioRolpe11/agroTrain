"""
Guarda de invariantes SPL sobre el UVL *activo de producción*.

El resto de la suite valida la lógica del configurador contra el fixture mínimo
`test_min.uvl`. Estas pruebas, en cambio, cargan el modelo real
(`v2_olivos_tratamientos.uvl`) y comprueban que sigue siendo satisfacible y que
respeta las convenciones de las que depende el pipeline de entrenamiento. Atrapan
el caso de "edité el UVL de producción y rompí una invariante" que el fixture
mínimo nunca vería.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.services.flamapy_service import FlamapyService

_BACKEND_DIR = Path(__file__).resolve().parents[3]
ACTIVE_UVL = _BACKEND_DIR / "uvl_versions" / "v2_olivos_tratamientos.uvl"
TEST_MIN_UVL = Path(__file__).resolve().parent / "fixtures" / "test_min.uvl"

TREATMENTS = ("RiegoControl", "RiegoDeficitario", "RiegoDeficitarioSevero")
TARGETS = ("TasaBuenos", "TasaSeveros", "MCD")
TELEMETRY_INDICES = ("NDVI", "EVI", "SAVI", "NDWI")


@pytest.fixture
def active_uvl():
    """Calienta el UVL de producción y restaura el fixture mínimo al terminar.

    `warm_up` muta estado de clase global; sin la restauración, las pruebas
    posteriores de la sesión que asumen `test_min.uvl` fallarían.
    """
    FlamapyService.warm_up(ACTIVE_UVL)
    yield FlamapyService
    if TEST_MIN_UVL.exists():
        FlamapyService.warm_up(TEST_MIN_UVL)


class TestActiveUvlSmoke:
    def test_active_uvl_file_exists(self):
        assert ACTIVE_UVL.exists(), f"UVL activo no encontrado: {ACTIVE_UVL}"

    def test_active_uvl_is_satisfiable(self, active_uvl):
        service = FlamapyService(ACTIVE_UVL)
        assert service.satisfiable() is True
        assert service.configurations_number() > 0

    def test_no_critical_dead_features(self, active_uvl):
        service = FlamapyService(ACTIVE_UVL)
        dead = set(service.dead_features())
        # Tratamientos, objetivos e índices de telemetría deben poder seleccionarse.
        assert dead.isdisjoint(TREATMENTS), f"Tratamientos muertos: {dead & set(TREATMENTS)}"
        assert dead.isdisjoint(TARGETS), f"Objetivos muertos: {dead & set(TARGETS)}"
        assert dead.isdisjoint(TELEMETRY_INDICES), f"Índices muertos: {dead & set(TELEMETRY_INDICES)}"

    @pytest.mark.parametrize("treatment", TREATMENTS)
    def test_each_treatment_admits_a_valid_config(self, active_uvl, treatment):
        service = FlamapyService(ACTIVE_UVL)
        base = ACTIVE_UVL.read_text(encoding="utf-8")
        constrained = base.rstrip() + "\n\t" + treatment + "\n"
        assert service.satisfiable(constrained) is True, (
            f"El tratamiento {treatment!r} no admite ninguna configuración válida."
        )


class TestSubtreeFeatureNames:
    def test_treatments_present(self, active_uvl):
        names = set(FlamapyService.get_subtree_feature_names("Tratamiento"))
        assert set(TREATMENTS) <= names

    def test_targets_present(self, active_uvl):
        names = set(FlamapyService.get_subtree_feature_names("VariableObjetivo"))
        assert set(TARGETS) <= names


class TestObjectiveColumnConvention:
    """Convención de entrenamiento: el nombre de cada VariableObjetivo es exactamente
    la columna CSV que `_features_to_training_params` busca en el CSV fusionado.
    Esa columna la produce un sensor del dendrómetro (DatoTB/DatoTS/DatoMCD)."""

    def test_each_target_name_is_a_sensor_csv_column(self, active_uvl):
        sensor_cols: set[str] = set()
        for feat in FlamapyService.get_subtree_feature_names("ParametrosEntrada"):
            sensor_cols.update(FlamapyService.get_csv_columns(feat))

        for target in FlamapyService.get_subtree_feature_names("VariableObjetivo"):
            assert target in sensor_cols, (
                f"El objetivo {target!r} no coincide con ninguna columna CSV de sensor; "
                f"rompe la convención nombre-objetivo == columna de entrenamiento."
            )
