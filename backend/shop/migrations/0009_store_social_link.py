from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_social_links(apps, schema_editor):
    SiteSetting = apps.get_model("shop", "SiteSetting")
    StoreSocialLink = apps.get_model("shop", "StoreSocialLink")
    for setting in SiteSetting.objects.all():
        if setting.social_links_migrated:
            continue
        order = 0
        if setting.facebook_url:
            StoreSocialLink.objects.create(
                site=setting,
                name="Facebook",
                url=setting.facebook_url,
                sort_order=order,
                is_active=True,
            )
            order += 1
        if setting.instagram_url:
            StoreSocialLink.objects.create(
                site=setting,
                name="Instagram",
                url=setting.instagram_url,
                sort_order=order,
                is_active=True,
            )
        setting.social_links_migrated = True
        setting.save(update_fields=["social_links_migrated"])


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0008_rate_observation"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesetting",
            name="social_links_migrated",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="StoreSocialLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("url", models.URLField(max_length=500)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_links",
                        to="shop.sitesetting",
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.RunPython(copy_legacy_social_links, migrations.RunPython.noop),
    ]
