from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import CustomUserManager

ROLE_TECNICO = "tecnico"
ROLE_ADMIN = "administrador"

ROLE_CHOICES = [
    (ROLE_TECNICO, "Técnico"),
    (ROLE_ADMIN, "Administrador"),
]


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TECNICO)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre", "role"]

    objects = CustomUserManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} <{self.email}>"

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN
