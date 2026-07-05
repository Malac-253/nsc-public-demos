"""Delete all expenses for the Brock Trip demo (one-time cleanup on Render)."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from party.models import Expense, Trip


class Command(BaseCommand):
    help = "Remove every expense on the Brock Trip (and their shares). Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trip-slug",
            default="brock-trip-2026",
            help="Trip slug to clear (default: brock-trip-2026)",
        )

    def handle(self, *args, **options):
        trip = Trip.objects.filter(slug=options["trip_slug"]).first()
        if not trip:
            self.stdout.write(self.style.WARNING(f"No trip with slug {options['trip_slug']!r}."))
            return
        qs = Expense.objects.filter(trip=trip)
        count = qs.count()
        if not count:
            self.stdout.write("No expenses to delete.")
            return
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} expense(s) for {trip.name}."))
