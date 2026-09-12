from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rentshield_identity", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="identityverification",
            name="passport_photo",
            field=models.FileField(blank=True, null=True, upload_to="rentshield_identity/passports/"),
        ),
        migrations.AddField(
            model_name="identityverification",
            name="selfie_photo",
            field=models.FileField(blank=True, null=True, upload_to="rentshield_identity/selfies/"),
        ),
        migrations.AddField(
            model_name="identityverification",
            name="latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="identityverification",
            name="longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="identityverification",
            name="location_accuracy_m",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
