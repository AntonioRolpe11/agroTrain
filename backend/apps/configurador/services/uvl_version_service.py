from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from .flamapy_service import FlamapyService, PARTIAL_STEP_ORDER
from .uvl_serializer import to_uvl

logger = logging.getLogger(__name__)

REQUIRED_WIZARD_STEPS = set(PARTIAL_STEP_ORDER) - {"full"}
REQUIRED_ROOT_NODES = {"VariableObjetivo", "Tratamiento", "ParametrosEntrada", "DatosTelemetria"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _versions_dir() -> Path:
    d = Path(settings.UVL_VERSIONS_PATH)
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_uvl_text(uvl_text: str) -> list[str]:
    """
    Technical validation. Returns list of error strings (empty = valid).
    Does NOT check config compatibility.
    """
    errors: []= []
    try:
        from flamapy.metamodels.bdd_metamodel.transformations import FmToBDD
        from flamapy.metamodels.fm_metamodel.transformations import UVLReader
        from flamapy.metamodels.bdd_metamodel.operations import BDDSatisfiable, BDDDeadFeatures
    except ImportError:
        errors.append("Flamapy no disponible en este entorno.")
        return errors

    tmp = Path(tempfile.mktemp(suffix=".uvl"))
    try:
        tmp.write_text(uvl_text, encoding="utf-8")
        try:
            fm_model = UVLReader(str(tmp)).transform()
        except Exception as exc:
            errors.append(f"Error de sintaxis UVL: {exc}")
            return errors

        try:
            bdd = FmToBDD(fm_model).transform()
        except Exception as exc:
            errors.append(f"No se pudo construir el BDD: {exc}")
            return errors

        try:
            satisfiable = bool(BDDSatisfiable().execute(bdd).get_result())
        except Exception as exc:
            errors.append(f"Error evaluando satisfiabilidad: {exc}")
            return errors

        if not satisfiable:
            errors.append("El modelo UVL no es satisfiable (ninguna configuración válida).")
            return errors

        try:
            dead = BDDDeadFeatures().execute(bdd).get_result()
            dead_names = [getattr(f, "name", str(f)) for f in dead]
            if dead_names:
                errors.append(f"Dead features detectadas: {', '.join(dead_names)}")
        except Exception as exc:
            errors.append(f"Error comprobando dead features: {exc}")

        # Verify wizard_step fixed structure
        found_steps: set[str] = set()
        _collect_wizard_steps(fm_model.root, found_steps)
        missing_steps = REQUIRED_WIZARD_STEPS - found_steps
        if missing_steps:
            errors.append(f"wizard_step fijos ausentes: {', '.join(sorted(missing_steps))}")

        # Verify required root nodes exist
        all_names = set(FlamapyService._collect_all_feature_names(fm_model.root))
        missing_nodes = REQUIRED_ROOT_NODES - all_names
        if missing_nodes:
            errors.append(f"Nodos raíz requeridos ausentes: {', '.join(sorted(missing_nodes))}")

    finally:
        tmp.unlink(missing_ok=True)

    return errors


def _collect_wizard_steps(feature, found: set[str]) -> None:
    for attr in feature.get_attributes():
        if attr.name == "wizard_step" and attr.default_value:
            found.add(attr.default_value)
    for rel in feature.get_relations():
        for child in rel.children:
            _collect_wizard_steps(child, found)


def create_version(
    name: str,
    description: str,
    tree: dict,
    constraints_text: str,
    author=None,
) -> tuple[object, list[str]]:
    """
    Build UVL text from edited tree + constraints_text, validate, save if valid.
    Returns (UVLVersion instance, errors). If errors non-empty, instance is None.
    """
    from apps.configurador.models import UVLVersion

    # Merge constraints_text into tree as plain strings for to_uvl
    # to_uvl uses tree["constraints"][i]["ast"], so we parse the text lines
    # into AST via FlamapyService round-trip through a temp file
    uvl_text = _build_uvl_from_tree_and_text(tree, constraints_text)

    errors = validate_uvl_text(uvl_text)
    if errors:
        return None, errors

    file_hash = _sha256(uvl_text)

    # Avoid exact duplicates
    if UVLVersion.objects.filter(file_hash=file_hash).exists():
        existing = UVLVersion.objects.get(file_hash=file_hash)
        return existing, ["Ya existe una versión idéntica (mismo hash): " + existing.name]

    versions_dir = _versions_dir()
    import uuid
    filename = f"{uuid.uuid4()}.uvl"
    dest = versions_dir / filename
    dest.write_text(uvl_text, encoding="utf-8")

    version = UVLVersion.objects.create(
        name=name,
        description=description,
        file_path=filename,
        file_hash=file_hash,
        author=author,
        is_active=False,
        is_valid=True,
        validation_errors=[],
    )
    return version, []


def _build_uvl_from_tree_and_text(tree: dict, constraints_text: str) -> str:
    """
    Serialize tree to UVL using the serializer, then replace the constraints block
    with the raw constraints_text lines (one per line, UVL syntax).
    This avoids needing an AST parser for the text — Flamapy will validate it.
    """
    base = to_uvl({**tree, "constraints": []})  # tree without constraints
    lines = [line for line in constraints_text.strip().splitlines() if line.strip()]
    if not lines:
        return base
    constraints_block = "constraints\n" + "\n".join(f"\t{ln.strip()}" for ln in lines)
    return base + "\n" + constraints_block


def preview_activation(version_id: int) -> dict:
    """
    Returns which Configuracion records would become incompatible if version_id is activated.
    Synchronous check on all configs. Returns {total, affected: [{id, nombre, user, reason}]}.
    """
    from apps.configurador.models import Configuracion, UVLVersion

    version = UVLVersion.objects.get(pk=version_id)
    uvl_path = Path(settings.UVL_VERSIONS_PATH) / version.file_path

    # Temp warm-up to validate configs against new version
    try:
        from flamapy.metamodels.bdd_metamodel.transformations import FmToBDD
        from flamapy.metamodels.fm_metamodel.transformations import UVLReader
        from flamapy.metamodels.bdd_metamodel.operations import BDDSatisfiable

        fm_new = UVLReader(str(uvl_path)).transform()
        bdd_new = FmToBDD(fm_new).transform()
        all_names_new = set(FlamapyService._collect_all_feature_names(fm_new.root))
    except Exception as exc:
        return {"total": 0, "affected": [], "error": str(exc)}

    configs = Configuracion.objects.select_related("user").all()
    total = configs.count()
    affected = []

    for cfg in configs:
        features = cfg.features or []
        unknown = [f for f in features if f not in all_names_new]
        if unknown:
            affected.append({
                "id": cfg.id,
                "nombre": cfg.nombre,
                "user": str(cfg.user),
                "reason": f"Features no presentes en nueva versión: {', '.join(unknown)}",
            })
            continue

        # Check satisfiability with pinned features
        uvl_text = uvl_path.read_text(encoding="utf-8")
        pins = []
        for name in FlamapyService._collect_all_feature_names(fm_new.root):
            if name in features:
                pins.append(name)
            else:
                pins.append(f"!{name}")
        constrained = uvl_text.rstrip() + "\n" + "\n".join(f"\t{p}" for p in pins) + "\n"
        try:
            from apps.configurador.services.flamapy_service import _temp_uvl_file
            with _temp_uvl_file(constrained) as tmp:
                fm_tmp = UVLReader(str(tmp)).transform()
                bdd_tmp = FmToBDD(fm_tmp).transform()
                valid = bool(BDDSatisfiable().execute(bdd_tmp).get_result())
        except Exception:
            valid = False

        if not valid:
            affected.append({
                "id": cfg.id,
                "nombre": cfg.nombre,
                "user": str(cfg.user),
                "reason": "La selección de features no satisface las constraints de la nueva versión.",
            })

    return {"total": total, "affected": affected}


def activate_version(version_id: int, confirm_incompatible: bool = False) -> tuple[bool, str, dict | None]:
    """
    Activate a UVLVersion.
    Returns (success, error_message, preview_report).
    preview_report is set when confirm_incompatible=False and there are affected configs.
    """
    from apps.configurador.models import Configuracion, UVLVersion
    from apps.modelos.services.training_service import _registry, _lock

    # Block if any training is active
    with _lock:
        active_trainings = [k for k, v in _registry.items() if v.get("status") == "training"]
    if active_trainings:
        return False, f"Hay {len(active_trainings)} entrenamiento(s) en curso. Espera a que terminen.", None

    version = UVLVersion.objects.get(pk=version_id)
    if not version.is_valid:
        return False, "Esta versión tiene errores de validación y no puede activarse.", None

    # Preview incompatible configs
    report = preview_activation(version_id)
    if report.get("affected") and not confirm_incompatible:
        return False, "Hay configuraciones incompatibles. Usa confirm_incompatible=true para confirmar.", report

    uvl_path = Path(settings.UVL_VERSIONS_PATH) / version.file_path

    # Mark affected configs as obsolete
    if report.get("affected"):
        affected_ids = [a["id"] for a in report["affected"]]
        Configuracion.objects.filter(pk__in=affected_ids).update(
            is_obsolete=True,
            obsolete_reason=f"Versión UVL activada: {version.name}",
        )

    # Swap active flag
    UVLVersion.objects.filter(is_active=True).update(is_active=False)
    version.is_active = True
    version.save(update_fields=["is_active"])

    # Hot-reload Flamapy
    try:
        FlamapyService.warm_up(uvl_path, version_id=version.pk)
    except Exception as exc:
        return False, f"Error recargando Flamapy: {exc}", None

    logger.info("UVL version %s (%s) activada.", version.pk, version.name)
    return True, "", report


def seed_initial_version(source_uvl_path: Path) -> None:
    """Create version 1 from the legacy agroTrain.uvl if no versions exist."""
    from apps.configurador.models import UVLVersion

    if UVLVersion.objects.exists():
        return

    uvl_text = source_uvl_path.read_text(encoding="utf-8")
    file_hash = _sha256(uvl_text)
    versions_dir = _versions_dir()
    dest = versions_dir / "v1_initial.uvl"
    if not dest.exists():
        shutil.copy2(source_uvl_path, dest)

    UVLVersion.objects.create(
        name="Versión inicial",
        description="Importada automáticamente desde agroTrain.uvl al arrancar.",
        file_path="v1_initial.uvl",
        file_hash=file_hash,
        author=None,
        is_active=True,
        is_valid=True,
        validation_errors=[],
    )
    logger.info("Versión UVL inicial creada desde %s", source_uvl_path)
