import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IdentityVerification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(default='idswyft', max_length=32)),
                ('verification_id', models.CharField(blank=True, default='', max_length=255)),
                ('hosted_url', models.URLField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('verified', 'Verified'), ('failed', 'Failed'), ('manual_review', 'Needs manual review')], default='pending', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rentshield_identity_verification', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
