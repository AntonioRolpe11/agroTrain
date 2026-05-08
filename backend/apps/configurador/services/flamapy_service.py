from __future__ import annotations

import contextlib
import logging
import tempfile
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

try:
    from flamapy.metamodels.bdd_metamodel.operations import (
        BDDConfigurationsNumber,
        BDDDeadFeatures,
        BDDSatisfiable,
    )
    from flamapy.metamodels.bdd_metamodel.transformations import FmToBDD
    from flamapy.metamodels.fm_metamodel.transformations import UVLReader
except Exception:  # pragma: no cover
    BDDConfigurationsNumber = None  # type: ignore[assignment]
    BDDDeadFeatures = None  # type: ignore[assignment]
    BDDSatisfiable = None  # type: ignore[assignment]
    FmToBDD = None  # type: ignore[assignment]
    UVLReader = None  # type: ignore[assignment]


# Ordering of wizard steps — UI concern, not derivable from UVL structure alone.
PARTIAL_STEP_ORDER = ("parcel", "sensors", "telemetry", "objective", "full")


@contextlib.contextmanager
def _temp_uvl_file(content: str) -> Generator[Path, None, None]:
    tmp = Path(tempfile.mktemp(suffix=".uvl"))
    try:
        tmp.write_text(content, encoding="utf-8")
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


class FlamapyService:
    _base_bdd_model = None
    _base_fm_model = None
    _all_feature_names: list[str] | None = None

    # Derived from UVL at warm_up — no hardcoded mirrors
    _labels: dict[str, str] = {}
    _partial_scope_features: dict[str, list[str]] = {}

    # Active version tracking — updated on every warm_up
    _active_path: Path | None = None
    _active_version_id: int | None = None

    def __init__(self, default_model_path: Path) -> None:
        self.default_model_path = default_model_path.resolve()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    @classmethod
    def warm_up(cls, path: Path, version_id: int | None = None) -> None:
        cls._ensure_dependencies()
        resolved = path.resolve()
        fm_model = UVLReader(str(resolved)).transform()  # type: ignore[misc]
        cls._base_bdd_model = FmToBDD(fm_model).transform()  # type: ignore[misc]
        cls._base_fm_model = fm_model
        cls._all_feature_names = cls._collect_all_feature_names(fm_model.root)
        cls._labels = cls._collect_labels()
        cls._partial_scope_features = cls._derive_partial_scope_features()
        cls._active_path = resolved
        cls._active_version_id = version_id
        logger.debug("BDD preconstruido desde %s (version_id=%s)", resolved, version_id)

    # ------------------------------------------------------------------
    # Label derivation from UVL 'label' attributes
    # ------------------------------------------------------------------

    @classmethod
    def _collect_labels(cls) -> dict[str, str]:
        labels: dict[str, str] = {}
        cls._collect_labels_rec(cls._base_fm_model.root, labels)
        return labels

    @classmethod
    def _collect_labels_rec(cls, feature, labels: dict[str, str]) -> None:
        for attr in feature.get_attributes():
            if attr.name == "label" and attr.default_value:
                labels[feature.name] = attr.default_value
                break
        for relation in feature.get_relations():
            for child in relation.children:
                cls._collect_labels_rec(child, labels)

    @classmethod
    def get_label(cls, feature_name: str) -> str:
        return cls._labels.get(feature_name, feature_name)

    # ------------------------------------------------------------------
    # PARTIAL_SCOPE_FEATURES derivation from UVL 'wizard_step' attributes
    # ------------------------------------------------------------------

    @classmethod
    def _derive_partial_scope_features(cls) -> dict[str, list[str]]:
        scope: dict[str, list[str]] = {step: [] for step in PARTIAL_STEP_ORDER}
        unassigned: list[str] = []
        cls._assign_to_steps(cls._base_fm_model.root, scope, unassigned)
        # Features without a wizard_step ancestor (e.g. root Entrada) go to first step
        first_step = next(s for s in PARTIAL_STEP_ORDER if s != "full")
        scope[first_step] = unassigned + scope[first_step]
        return scope

    @classmethod
    def _assign_to_steps(cls, feature, scope: dict[str, list[str]], unassigned: list[str]) -> None:
        for attr in feature.get_attributes():
            if attr.name == "wizard_step" and attr.default_value:
                step = attr.default_value
                if step in scope:
                    scope[step].extend(cls._collect_all_feature_names(feature))
                return  # Entire subtree assigned; stop recursing
        unassigned.append(feature.name)
        for relation in feature.get_relations():
            for child in relation.children:
                cls._assign_to_steps(child, scope, unassigned)

    # ------------------------------------------------------------------
    # Generic constraint evaluation (mirrors frontend evalAST / getViolations)
    # ------------------------------------------------------------------

    @classmethod
    def _eval_ast(cls, node: dict, selected: set[str]) -> bool:
        op = node.get("op")
        if op == "FEATURE":
            return node["name"] in selected
        if op == "IMPLIES":
            return not cls._eval_ast(node["left"], selected) or cls._eval_ast(node["right"], selected)
        if op == "AND":
            return cls._eval_ast(node["left"], selected) and cls._eval_ast(node["right"], selected)
        if op == "OR":
            return cls._eval_ast(node["left"], selected) or cls._eval_ast(node["right"], selected)
        if op == "NOT":
            return not cls._eval_ast(node["left"], selected)
        return True

    @classmethod
    def _format_ast(cls, node: dict, parent_op: str | None = None) -> str:
        """Serialize an AST node to a human-readable Spanish string using feature labels."""
        op = node.get("op")
        if op == "FEATURE":
            return cls.get_label(node["name"])
        if op == "AND":
            left = cls._format_ast(node["left"], "AND")
            right = cls._format_ast(node["right"], "AND")
            result = f"{left} + {right}"
            # Parenthesize when nested inside OR to clarify precedence
            return f"({result})" if parent_op == "OR" else result
        if op == "OR":
            left = cls._format_ast(node["left"], "OR")
            right = cls._format_ast(node["right"], "OR")
            return f"{left} o {right}"
        if op == "NOT":
            return f"no {cls._format_ast(node['left'], 'NOT')}"
        return ""

    @classmethod
    def _collect_ast_features(cls, node: dict) -> set[str]:
        if node.get("op") == "FEATURE":
            return {node["name"]}
        result: set[str] = set()
        if "left" in node:
            result |= cls._collect_ast_features(node["left"])
        if "right" in node:
            result |= cls._collect_ast_features(node["right"])
        return result

    @classmethod
    def _get_violated_constraint_messages(cls, features: list[str], scope: set[str]) -> list[str]:
        """
        Evaluate IMPLIES constraints against the selected features.
        Only reports constraints where ALL features are within scope —
        mirrors the frontend getViolations(constraints, subtreeNames, activeFeatures) filter.
        """
        selected = set(features)
        messages: list[str] = []
        for constraint in cls._base_fm_model.get_constraints():
            ast = cls._serialize_ast_node(constraint.ast.root)
            if ast.get("op") != "IMPLIES":
                continue
            if not cls._collect_ast_features(ast).issubset(scope):
                continue
            left = ast.get("left", {})
            if left.get("op") != "FEATURE" or left["name"] not in selected:
                continue
            if cls._eval_ast(ast["right"], selected):
                continue
            antecedent_label = cls.get_label(left["name"])
            consequent_str = cls._format_ast(ast["right"])
            messages.append(f"{antecedent_label} requiere {consequent_str}.")
        return messages

    # ------------------------------------------------------------------
    # Feature tree traversal
    # ------------------------------------------------------------------

    @classmethod
    def _collect_all_feature_names(cls, feature) -> list[str]:
        names = [feature.name]
        for relation in feature.get_relations():
            for child in relation.children:
                names.extend(cls._collect_all_feature_names(child))
        return names

    @classmethod
    def _find_feature(cls, node, name: str):
        if node.name == name:
            return node
        for relation in node.get_relations():
            for child in relation.children:
                found = cls._find_feature(child, name)
                if found:
                    return found
        return None

    @classmethod
    def get_subtree_feature_names(cls, parent_name: str) -> list[str]:
        """All descendant feature names under parent_name (exclusive of parent), in UVL order."""
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        node = cls._find_feature(cls._base_fm_model.root, parent_name)
        if node is None:
            return []
        result: list[str] = []
        for relation in node.get_relations():
            for child in relation.children:
                result.extend(cls._collect_all_feature_names(child))
        return result

    @classmethod
    def get_csv_columns(cls, feature_name: str) -> list[str]:
        """CSV column name(s) for a feature, from its csv_col/csv_cols UVL attribute."""
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        node = cls._find_feature(cls._base_fm_model.root, feature_name)
        if node is None:
            return []
        for attr in node.get_attributes():
            if attr.name == "csv_col" and attr.default_value:
                return [attr.default_value]
            if attr.name == "csv_cols" and attr.default_value:
                return [c.strip() for c in attr.default_value.split(",")]
        return []

    @classmethod
    def get_quality_thresholds(cls, target_name: str) -> dict | None:
        """R² quality thresholds for an objective variable, from its quality_min/quality_good UVL attributes."""
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        node = cls._find_feature(cls._base_fm_model.root, target_name)
        if node is None:
            return None
        attrs = {attr.name: attr.default_value for attr in node.get_attributes() if attr.default_value}
        if "quality_min" not in attrs or "quality_good" not in attrs:
            return None
        return {"min": float(attrs["quality_min"]), "good": float(attrs["quality_good"])}

    _DEFAULT_TREATMENT_PROFILE: dict = {
        "window_size": 5,
        "preferred_algorithm": "RandomForest",
        "min_samples": 80,
    }

    @classmethod
    def get_treatment_profile(cls, treatment_name: str) -> dict:
        """Training profile for an olive irrigation treatment, derived from UVL attributes."""
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        node = cls._find_feature(cls._base_fm_model.root, treatment_name)
        if node is None:
            return dict(cls._DEFAULT_TREATMENT_PROFILE)
        attrs = {attr.name: attr.default_value for attr in node.get_attributes() if attr.default_value}
        profile = dict(cls._DEFAULT_TREATMENT_PROFILE)
        if "window_size" in attrs:
            profile["window_size"] = int(attrs["window_size"])
        if "preferred_algorithm" in attrs:
            profile["preferred_algorithm"] = attrs["preferred_algorithm"]
        if "min_samples" in attrs:
            profile["min_samples"] = int(attrs["min_samples"])
        return profile

    @classmethod
    def get_target_profile(cls, target_name: str) -> dict:
        """
        Per-target overrides derived from UVL attributes on the VariableObjetivo node.

        Read by training_service to override the treatment profile when the target
        declares a `preferred_algorithm` and/or `window_size_override`. The empirical
        rationale for these per-target overrides is documented in
        `docs/experimentacion_modelos.md` (sección "Reasignación del atributo
        preferred_algorithm" y "Window size variable por target").
        """
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        node = cls._find_feature(cls._base_fm_model.root, target_name)
        if node is None:
            return {}
        attrs = {attr.name: attr.default_value for attr in node.get_attributes() if attr.default_value}
        profile: dict = {}
        if "preferred_algorithm" in attrs:
            profile["preferred_algorithm"] = attrs["preferred_algorithm"]
        if "window_size_override" in attrs:
            profile["window_size"] = int(attrs["window_size_override"])
        return profile

    @classmethod
    def get_crop_profile(cls, crop_name: str) -> dict:
        """Backward-compatible alias for legacy callers; use get_treatment_profile."""
        return cls.get_treatment_profile(crop_name)

    # ------------------------------------------------------------------
    # Feature model serialization
    # ------------------------------------------------------------------

    @classmethod
    def to_dict(cls) -> dict:
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        return {
            **cls._to_dict_rec(cls._base_fm_model.root),
            "constraints": cls.get_constraints_json(),
        }

    @classmethod
    def get_constraints_json(cls) -> list[dict]:
        if cls._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")
        return [
            {
                "features": constraint.get_features(),
                "ast": cls._serialize_ast_node(constraint.ast.root),
            }
            for constraint in cls._base_fm_model.get_constraints()
        ]

    @classmethod
    def _serialize_ast_node(cls, node) -> dict:
        if node.is_term():
            return {"op": "FEATURE", "name": str(node.data)}
        op = node.data.name  # IMPLIES, OR, AND, NOT
        serialized: dict = {"op": op}
        if node.left is not None:
            serialized["left"] = cls._serialize_ast_node(node.left)
        if node.right is not None:
            serialized["right"] = cls._serialize_ast_node(node.right)
        return serialized

    @classmethod
    def _to_dict_rec(cls, feature) -> dict:
        attrs = {a.name: a.default_value for a in feature.get_attributes()}
        node: dict = {
            "name": feature.name,
            "relations": [
                {
                    "type": cls._relation_type(relation),
                    "children": [cls._to_dict_rec(child) for child in relation.children],
                }
                for relation in feature.get_relations()
            ],
        }
        if attrs:
            node["attributes"] = attrs
        return node

    @staticmethod
    def _relation_type(relation) -> str:
        if relation.is_or():
            return "OR"
        if relation.is_alternative():
            return "ALTERNATIVE"
        if relation.is_mandatory():
            return "MANDATORY"
        return "OPTIONAL"

    # ------------------------------------------------------------------
    # Public validation API
    # ------------------------------------------------------------------

    def validate_features(self, features: list[str], is_full: bool, step: str = "full") -> tuple[bool, list[str]]:
        """
        Validate a feature selection against the UVL model.

        is_full=True  → all non-selected features pinned to False (complete config check).
        is_full=False → step-aware partial check: features within the step's accumulated
                        scope but not selected are pinned to False; features outside the
                        scope are left free (deferring their validation to later steps).

        Error messages are derived generically from the UVL constraint ASTs and labels,
        filtered to constraints whose features are all within the evaluated scope.
        """
        self._ensure_dependencies()
        if self._base_fm_model is None:
            raise RuntimeError("Modelo no inicializado. Llama a warm_up primero.")

        features_set = set(features)
        all_names = self._all_feature_names or []
        uvl_path = self._active_path or self.default_model_path
        base_uvl = uvl_path.read_text(encoding="utf-8")

        if is_full:
            scope = set(all_names)
            pin_constraints = [name if name in features_set else f"!{name}" for name in all_names]
        else:
            scope = set(self._get_features_for_step(step))
            pin_constraints = []
            for name in all_names:
                if name in features_set:
                    pin_constraints.append(name)       # selected → True
                elif name in scope:
                    pin_constraints.append(f"!{name}") # in-scope, unselected → False
                # out of scope → free (no constraint added)

        if not pin_constraints:
            valid = self.satisfiable()
            return (valid, []) if valid else (False, ["El modelo no es satisfiable."])

        constrained_uvl = base_uvl.rstrip() + "\n" + "\n".join(f"\t{c}" for c in pin_constraints) + "\n"
        if self.satisfiable(constrained_uvl):
            return True, []

        errors = self._get_violated_constraint_messages(features, scope)
        if not errors:
            errors = [
                "La configuración no es válida según el modelo UVL."
                if is_full
                else "La selección actual no puede completarse de forma válida según el modelo UVL."
            ]
        return False, errors

    def satisfiable(self, uvl: str | None = None) -> bool:
        self._ensure_dependencies()
        bdd = self._build_bdd_model(uvl)
        return bool(BDDSatisfiable().execute(bdd).get_result())  # type: ignore[misc]

    def configurations_number(self, uvl: str | None = None) -> int:
        self._ensure_dependencies()
        bdd = self._build_bdd_model(uvl)
        return int(BDDConfigurationsNumber().execute(bdd).get_result())  # type: ignore[misc]

    def dead_features(self, uvl: str | None = None) -> list[str]:
        self._ensure_dependencies()
        bdd = self._build_bdd_model(uvl)
        dead = BDDDeadFeatures().execute(bdd).get_result()  # type: ignore[misc]
        return [getattr(f, "name", str(f)) for f in dead]

    # ------------------------------------------------------------------
    # BDD construction
    # ------------------------------------------------------------------

    def _build_bdd_model(self, uvl: str | None):
        self._ensure_dependencies()
        if uvl is None:
            if self._base_bdd_model is not None:
                return self._base_bdd_model
            if not self.default_model_path.exists():
                raise FileNotFoundError(f"No se encontró el modelo UVL: {self.default_model_path}")
            fm_model = UVLReader(str(self.default_model_path)).transform()  # type: ignore[misc]
            return FmToBDD(fm_model).transform()  # type: ignore[misc]
        with _temp_uvl_file(uvl) as tmp_path:
            fm_model = UVLReader(str(tmp_path)).transform()  # type: ignore[misc]
            return FmToBDD(fm_model).transform()  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Step-aware feature scoping (used by validate_features partial mode)
    # ------------------------------------------------------------------

    def _get_features_for_step(self, step: str) -> list[str]:
        features: list[str] = []
        scope = self._partial_scope_features
        for current_step in PARTIAL_STEP_ORDER:
            features.extend(scope.get(current_step, []))
            if current_step == step:
                break
        return features

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_dependencies() -> None:
        if any(dep is None for dep in [UVLReader, FmToBDD, BDDSatisfiable, BDDConfigurationsNumber, BDDDeadFeatures]):
            raise RuntimeError(
                "Flamapy no está instalado. Ejecuta: pip install -r backend/requirements/base.txt"
            )
