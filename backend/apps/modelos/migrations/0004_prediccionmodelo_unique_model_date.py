from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("modelos", "0003_rename_crop_to_treatment"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="prediccionmodelo",
            unique_together={("model", "predicted_for_date")},
        ),
        migrations.AlterModelOptions(
            name="prediccionmodelo",
            options={"ordering": ["-predicted_for_date", "-generated_at"]},
        ),
    ]
