from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("modelos", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="modeloguardado",
            name="features",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="modeloguardado",
            name="geo",
            field=models.JSONField(default=dict),
        ),
        migrations.CreateModel(
            name="PrediccionModelo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("predicted_for_date", models.DateField()),
                ("predictions", models.JSONField()),
                ("input_row_count", models.IntegerField(default=0)),
                ("warnings", models.JSONField(default=list)),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="predicciones",
                        to="modelos.modeloguardado",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="predicciones_modelos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at"],
            },
        ),
    ]
