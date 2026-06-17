"""
Reset DB + Flamapy state to a known fixture for E2E tests.

Used by Cypress `cy.task("resetBackend")` before every spec so that test runs
are deterministic and isolated, mirroring the pattern recommended for E2E
suites that cross the frontend/backend boundary.

Workflow:
    1. Flush the development DB.
    1b. Purge on-disk model_storage artifacts (orphaned by the DB flush).
    2. Apply migrations.
    3. Seed a deterministic admin + tecnico user.
    4. Activate the canonical UVL fixture (`v2_olivos_tratamientos.uvl`) as the
       only `is_active=True` UVLVersion row.
    5. Re-build the in-memory Flamapy BDD against that file.

Invocation:
    python manage.py reset_test_state            # seeds and reports text summary
    python manage.py reset_test_state --json     # prints {"admin": ..., "tecnico": ...}

Never call this in production. The command refuses to run unless DEBUG=True.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


DEFAULT_UVL = "v2_olivos_tratamientos.uvl"
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "admin1234"
TECNICO_EMAIL = "tecnico@test.local"
TECNICO_PASSWORD = "tecnico1234"


class Command(BaseCommand):
    help = "Reset the DB and Flamapy state for E2E tests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output the seeded credentials as JSON (consumed by Cypress).",
        )
        parser.add_argument(
            "--uvl",
            default=DEFAULT_UVL,
            help=f"UVL file name under uvl_versions/ to activate (default: {DEFAULT_UVL}).",
        )
        parser.add_argument(
            "--allow-prod",
            action="store_true",
            help="Skip the DEBUG-only guard. DANGEROUS; only for trusted CI envs.",
        )

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["allow_prod"]:
            raise CommandError(
                "reset_test_state aborted: DEBUG is False. Use --allow-prod to override."
            )

        from apps.accounts.models import ROLE_ADMIN, ROLE_TECNICO, CustomUser
        from apps.configurador.models import UVLVersion
        from apps.configurador.services.flamapy_service import FlamapyService
        from apps.configurador.services.uvl_version_service import _sha256

        uvl_versions_dir = Path(settings.UVL_VERSIONS_PATH)
        target_uvl = uvl_versions_dir / opts["uvl"]
        if not target_uvl.exists():
            raise CommandError(f"UVL fixture not found: {target_uvl}")

        # 1. Flush DB content (keeps the migration history)
        call_command("flush", "--no-input", verbosity=0)

        # 1b. Purge on-disk artifacts of E2E-created models only. flush drops the
        # ModeloGuardado rows but the model_storage/<uuid>/ dirs (metadata.json +
        # .pkl) persist, leaving orphans across runs. We delete ONLY dirs whose
        # metadata marks them as test models (geo.nombre contains "E2E"), so a
        # developer's own models in the same store survive.
        storage = Path(settings.MODELS_STORAGE_PATH)
        if storage.exists():
            for child in storage.iterdir():
                if not child.is_dir():
                    continue
                meta_file = child / "metadata.json"
                if not meta_file.exists():
                    continue
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                nombre = (meta.get("geo") or {}).get("nombre") or ""
                if "E2E" in nombre:
                    shutil.rmtree(child, ignore_errors=True)

        # 2. Apply migrations (idempotent — needed if a fresh sqlite file is in use)
        call_command("migrate", "--no-input", verbosity=0)

        # 3. Seed deterministic users
        admin = CustomUser.objects.create_user(
            email=ADMIN_EMAIL, password=ADMIN_PASSWORD, nombre="Admin E2E", role=ROLE_ADMIN
        )
        tecnico = CustomUser.objects.create_user(
            email=TECNICO_EMAIL, password=TECNICO_PASSWORD, nombre="Tecnico E2E", role=ROLE_TECNICO
        )

        # 4. Ensure target UVL is registered + active
        uvl_text = target_uvl.read_text(encoding="utf-8")
        file_hash = _sha256(uvl_text)
        UVLVersion.objects.filter(is_active=True).update(is_active=False)
        version, _ = UVLVersion.objects.get_or_create(
            file_hash=file_hash,
            defaults={
                "name": opts["uvl"],
                "description": "E2E reset fixture",
                "file_path": opts["uvl"],
                "author": admin,
                "is_active": True,
                "is_valid": True,
                "validation_errors": [],
            },
        )
        if not version.is_active:
            version.is_active = True
            version.save(update_fields=["is_active"])

        # 5. Rebuild BDD
        FlamapyService.warm_up(target_uvl, version_id=version.pk)

        creds = {
            "admin": {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "id": admin.pk},
            "tecnico": {"email": TECNICO_EMAIL, "password": TECNICO_PASSWORD, "id": tecnico.pk},
            "uvl_version_id": version.pk,
            "uvl_path": str(target_uvl),
        }

        if opts["json"]:
            self.stdout.write(json.dumps(creds))
        else:
            self.stdout.write(self.style.SUCCESS("State reset OK."))
            self.stdout.write(f"  admin    : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
            self.stdout.write(f"  tecnico  : {TECNICO_EMAIL} / {TECNICO_PASSWORD}")
            self.stdout.write(f"  UVL      : {target_uvl}")
