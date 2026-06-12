from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configurador", "0003_activate_olivos_tratamientos_uvl"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uvlversion",
            name="file_hash",
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
