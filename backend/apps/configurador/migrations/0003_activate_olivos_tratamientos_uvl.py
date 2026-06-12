from django.db import migrations


UVL_FILE = "v2_olivos_tratamientos.uvl"
UVL_HASH = "5c208fbbcfae32b5b0cf838a9f3db8ccc01f84f778c23719c50f96113f91aad5"
UVL_NAME = "Olivos con tratamientos de riego"


def activate_olivos_tratamientos(apps, schema_editor):
    UVLVersion = apps.get_model("configurador", "UVLVersion")
    Configuracion = apps.get_model("configurador", "Configuracion")

    version, _created = UVLVersion.objects.get_or_create(
        file_path=UVL_FILE,
        defaults={
            "name": UVL_NAME,
            "description": (
                "Modelo UVL centrado exclusivamente en olivos, con tratamientos "
                "Riego control, Riego deficitario y Riego deficitario severo."
            ),
            "file_hash": UVL_HASH,
            "author": None,
            "is_active": False,
            "is_valid": True,
            "validation_errors": [],
        },
    )
    UVLVersion.objects.exclude(pk=version.pk).update(is_active=False)
    UVLVersion.objects.filter(pk=version.pk).update(
        name=UVL_NAME,
        file_hash=UVL_HASH,
        is_active=True,
        is_valid=True,
        validation_errors=[],
    )
    Configuracion.objects.exclude(uvl_version=version).update(
        is_obsolete=True,
        obsolete_reason=(
            "Versión UVL activada: olivos con tratamientos de riego. "
            "Las configuraciones basadas en cultivos anteriores deben recrearse."
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("configurador", "0002_uvlversion_configuracion_uvl_fields"),
    ]

    operations = [
        migrations.RunPython(activate_olivos_tratamientos, migrations.RunPython.noop),
    ]
