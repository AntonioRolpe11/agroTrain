from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from apps.accounts.models import ROLE_ADMIN, CustomUser


class Command(BaseCommand):
    help = (
        "Crea el usuario administrador inicial de forma idempotente. "
        "Las credenciales se leen de variables de entorno; si ya existe se omite. "
        "El resto de usuarios (técnicos) los crea el administrador desde la aplicación."
    )

    def handle(self, *args, **options):
        email = os.environ.get("SEED_ADMIN_EMAIL", "admin@agrotrain.local")
        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(f"Administrador ya existe, omitido: {email}")
            return
        CustomUser.objects.create_superuser(
            email=email,
            password=os.environ.get("SEED_ADMIN_PASSWORD", "admin"),
            nombre=os.environ.get("SEED_ADMIN_NOMBRE", "Administrador"),
            role=ROLE_ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f"Administrador creado: {email}"))
