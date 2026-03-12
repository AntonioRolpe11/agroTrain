from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configurador", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UVLVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("file_path", models.CharField(max_length=500)),
                ("file_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=False)),
                ("is_valid", models.BooleanField(default=True)),
                ("validation_errors", models.JSONField(default=list)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uvl_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="configuracion",
            name="uvl_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="configuraciones",
                to="configurador.uvlversion",
            ),
        ),
        migrations.AddField(
            model_name="configuracion",
            name="is_obsolete",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="configuracion",
            name="obsolete_reason",
            field=models.TextField(blank=True),
        ),
    ]
