from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0007_original_prices_fx_and_trader_discounts"),
    ]

    operations = [
        migrations.CreateModel(
            name="RateObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="frankfurter", max_length=40)),
                ("provider_date", models.DateField()),
                ("fetched_at", models.DateTimeField()),
                ("cny_per_usd", models.DecimalField(decimal_places=8, max_digits=18)),
                ("ils_per_usd", models.DecimalField(decimal_places=8, max_digits=18)),
            ],
            options={
                "ordering": ["-provider_date", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="rateobservation",
            constraint=models.UniqueConstraint(fields=("provider", "provider_date"), name="unique_fx_daily_observation"),
        ),
        migrations.AddConstraint(
            model_name="rateobservation",
            constraint=models.CheckConstraint(condition=models.Q(("cny_per_usd__gt", 0)), name="fx_observation_cny_positive"),
        ),
        migrations.AddConstraint(
            model_name="rateobservation",
            constraint=models.CheckConstraint(condition=models.Q(("ils_per_usd__gt", 0)), name="fx_observation_ils_positive"),
        ),
        migrations.AddIndex(
            model_name="rateobservation",
            index=models.Index(fields=["provider_date"], name="fx_observation_date_idx"),
        ),
    ]
