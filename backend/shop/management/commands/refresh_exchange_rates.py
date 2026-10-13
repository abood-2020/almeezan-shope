from django.core.management.base import BaseCommand

from shop.fx import refresh_exchange_rates


class Command(BaseCommand):
    help = "Fetch CNY, USD and ILS rates from Frankfurter and publish one snapshot."

    def handle(self, *args, **options):
        result = refresh_exchange_rates()
        snapshot = result["snapshot"]
        if result["ok"]:
            when = snapshot.provider_date.isoformat() if snapshot else ""
            self.stdout.write(self.style.SUCCESS(f"Exchange rates saved. Provider date {when}."))
            return
        self.stderr.write(f"Exchange rate refresh failed: {result['error']}. The previous snapshot was kept.")
        raise SystemExit(1)
