from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("modelos", "0002_prediction_metadata"),
    ]

    operations = [
        migrations.RenameField(
            model_name="modeloguardado",
            old_name="crop",
            new_name="treatment",
        ),
    ]
