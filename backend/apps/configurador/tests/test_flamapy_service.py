from __future__ import annotations

from pathlib import Path

import pytest

from apps.configurador.services.flamapy_service import FlamapyService, PARTIAL_STEP_ORDER


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_min.uvl"


class TestFlamapyServiceWarmUp:
    def test_warmup_idempotent(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService._base_fm_model is not None

    def test_warmup_records_active_path(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService._active_path == FIXTURE_PATH.resolve()


class TestLabels:
    def test_get_label_returns_uvl_label(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_label("Secano") == "Secano"
        assert FlamapyService.get_label("Tratamiento") == "Tratamiento de riego"

    def test_get_label_falls_back_to_feature_name(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_label("DoesNotExist") == "DoesNotExist"


class TestSubtreeAccess:
    def test_get_subtree_feature_names_tratamiento(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        names = FlamapyService.get_subtree_feature_names("Tratamiento")
        assert "Secano" in names
        assert "RiegoControl" in names
        assert "Tratamiento" not in names  # exclusive of parent

    def test_get_subtree_feature_names_variable_objetivo(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        names = FlamapyService.get_subtree_feature_names("VariableObjetivo")
        assert set(names) >= {"MCD", "TasaBuenos"}

    def test_get_subtree_unknown_returns_empty(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_subtree_feature_names("NoSuch") == []


class TestCsvColumns:
    def test_get_csv_columns_single(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_csv_columns("DatoMCD") == ["MCD"]

    def test_get_csv_columns_multiple(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        cols = FlamapyService.get_csv_columns("TemperaturaAire")
        assert cols == ["tmax", "tmin"]

    def test_get_csv_columns_returns_empty_when_absent(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_csv_columns("Tratamiento") == []


class TestProfiles:
    def test_get_treatment_profile_secano(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        profile = FlamapyService.get_treatment_profile("Secano")
        assert profile["window_size"] == 5
        assert profile["preferred_algorithm"] == "RandomForest"
        assert profile["min_samples"] == 20

    def test_get_treatment_profile_unknown_returns_defaults(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        profile = FlamapyService.get_treatment_profile("Nope")
        assert profile["window_size"] == 5
        assert profile["preferred_algorithm"] == "RandomForest"

    def test_get_target_profile_with_override(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        profile = FlamapyService.get_target_profile("TasaBuenos")
        assert profile["preferred_algorithm"] == "RandomForest"
        assert profile["window_size"] == 7

    def test_get_target_profile_empty_when_no_attrs(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_target_profile("MCD") == {}

    def test_get_quality_thresholds(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        th = FlamapyService.get_quality_thresholds("MCD")
        assert th == {"min": 0.35, "good": 0.50}

    def test_get_quality_thresholds_none_when_absent(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        assert FlamapyService.get_quality_thresholds("Secano") is None


class TestValidateFeatures:
    def test_valid_full_configuration(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        features = [
            "Entrada",
            "DatosParcela",
            "Tratamiento", "Secano",
            "TipoSuelo", "Vertisoles",
            "ParametrosEntrada",
            "Dendrometro", "DatoMCD",
            "DatosTelemetria", "Nubes",
            "VariableObjetivo", "MCD",
        ]
        valid, errors = service.validate_features(features, is_full=True)
        assert valid is True
        assert errors == []

    def test_invalid_configuration_returns_constraint_error(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        # MCD target without DatoMCD sensor → violates MCD => DatoMCD
        features = [
            "Entrada",
            "DatosParcela", "Tratamiento", "Secano", "TipoSuelo", "Vertisoles",
            "ParametrosEntrada", "Dendrometro", "DatoTB",
            "DatosTelemetria", "Nubes",
            "VariableObjetivo", "MCD",
        ]
        valid, errors = service.validate_features(features, is_full=True)
        assert valid is False
        assert any("MCD" in err for err in errors)

    def test_partial_validation_defers_out_of_scope(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        # Only parcel-step features selected — should pass because sensors/objective are not in scope
        features = ["Entrada", "DatosParcela", "Tratamiento", "Secano", "TipoSuelo", "Vertisoles"]
        valid, errors = service.validate_features(features, is_full=False, step="parcel")
        assert valid is True

    def test_partial_validation_blocks_cross_step_violation(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        # RiegoControl requires TemperaturaAire — checked once sensors step is reached.
        features = [
            "Entrada",
            "DatosParcela", "Tratamiento", "RiegoControl", "TipoSuelo", "Vertisoles",
            "ParametrosEntrada", "Dendrometro", "DatoMCD",  # missing TemperaturaAire
        ]
        valid, errors = service.validate_features(features, is_full=False, step="sensors")
        assert valid is False
        assert any("Temperatura" in e or "TemperaturaAire" in e for e in errors)


class TestBddOperations:
    def test_satisfiable_base_model(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        assert service.satisfiable() is True

    def test_configurations_number_is_positive(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        assert service.configurations_number() > 0

    def test_dead_features_returns_list(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        service = FlamapyService(FIXTURE_PATH)
        result = service.dead_features()
        assert isinstance(result, list)


class TestSerialization:
    def test_to_dict_returns_tree_with_constraints(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        tree = FlamapyService.to_dict()
        assert tree["name"] == "Entrada"
        assert "relations" in tree
        assert isinstance(tree["constraints"], list)
        assert len(tree["constraints"]) > 0

    def test_constraint_serialization_has_ast(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        constraints = FlamapyService.get_constraints_json()
        assert all("ast" in c and "features" in c for c in constraints)
        assert any(c["ast"]["op"] == "IMPLIES" for c in constraints)


class TestPartialStepScope:
    def test_partial_scope_covers_all_steps(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        scope = FlamapyService._partial_scope_features
        for step in ("parcel", "sensors", "telemetry", "objective"):
            assert step in scope
            assert len(scope[step]) > 0

    def test_step_order_includes_full(self):
        assert "full" in PARTIAL_STEP_ORDER
        assert PARTIAL_STEP_ORDER[0] == "parcel"


class TestTreatmentTargetProfile:
    def test_falls_back_to_treatment_defaults(self):
        FlamapyService.warm_up(FIXTURE_PATH)
        # No pref_alg_MCD / window_MCD on Secano → uses treatment defaults
        profile = FlamapyService.get_treatment_target_profile("Secano", "MCD")
        assert profile["algorithm"] == "RandomForest"
        assert profile["window_size"] == 5
        assert profile["feature_variant"] is None
        assert profile["hyperprofile"] is None

    def test_uses_treatment_pertarget_attrs_when_present(self, tmp_path):
        # Build a UVL with treatment-per-target attrs
        uvl = """namespace t
features
\tRoot
\t\tmandatory
\t\t\tT { window_size 4, preferred_algorithm 'RandomForest', min_samples 10, pref_alg_X 'XGBoost', window_X 9, feat_variant_X 'ema', hyperprofile_X 'hp_x_v1' }
\t\t\tX { csv_col 'x' }
"""
        path = tmp_path / "t.uvl"
        path.write_text(uvl, encoding="utf-8")
        FlamapyService.warm_up(path)
        profile = FlamapyService.get_treatment_target_profile("T", "X")
        assert profile["algorithm"] == "XGBoost"
        assert profile["window_size"] == 9
        assert profile["feature_variant"] == "ema"
        assert profile["hyperprofile"] == "hp_x_v1"
        # Re-warm with the original fixture for downstream tests
        FlamapyService.warm_up(FIXTURE_PATH)
