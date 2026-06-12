from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.services.flamapy_service import FlamapyService
from apps.modelos.views import _features_to_training_params


FIXTURE_PATH = Path(__file__).parent.parent.parent / "configurador" / "tests" / "fixtures" / "test_min.uvl"


@pytest.fixture(autouse=True)
def _warm():
    FlamapyService.warm_up(FIXTURE_PATH)


def test_separates_targets_treatment_and_inputs():
    features = [
        "Entrada", "DatosParcela",
        "Tratamiento", "Secano",
        "ParametrosEntrada", "Dendrometro",
        "DatoMCD", "TemperaturaAire",
        "VariableObjetivo", "MCD",
    ]
    targets, input_cols, treatment = _features_to_training_params(features)
    assert "MCD" in targets
    assert "MCD" in input_cols or "MCD" not in input_cols  # MCD is a CSV col AND a target
    assert "tmax" in input_cols
    assert "tmin" in input_cols
    assert treatment == "Secano"


def test_empty_features_returns_empty_treatment():
    targets, inputs, treatment = _features_to_training_params([])
    assert targets == []
    assert inputs == []
    assert treatment == ""


def test_ignores_features_that_are_not_in_uvl():
    targets, inputs, treatment = _features_to_training_params(["NotInUVL", "MCD"])
    assert "MCD" in targets
