from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError

from shop.fx import FxError, backfill_exchange_rates


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CommandError("Dates must use YYYY-MM-DD.") from exc


class Command(BaseCommand):
    help = "Import published Frankfurter USD/CNY and USD/ILS observations without changing the active snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True, type=_date)
        parser.add_argument("--end", required=False, type=_date)

    def handle(self, *args, **options):
        start = options["start"]
        end = options["end"]
        if not isinstance(start, date):
            raise CommandError("Dates must use YYYY-MM-DD.")
        try:
            result = backfill_exchange_rates(start, end)
        except FxError as exc:
            raise CommandError(f"Exchange rate backfill failed: {exc.code}.") from exc
        self.stdout.write(
            "Imported {imported}, skipped {skipped}, failed {failed}. Range {start} to {end}.".format(**{
                "imported": result["imported"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "start": result["start"].isoformat(),
                "end": result["end"].isoformat(),
            })
        )
