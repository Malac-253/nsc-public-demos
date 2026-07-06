"""Remove data left behind by _smoke.py (lists, notes, events, etc.)."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from party.models import Event, InfoPage, TaskList, Trip


class Command(BaseCommand):
    help = "Delete smoke-test lists, notes, and events from the Brock Trip."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trip-slug",
            default="brock-trip-2026",
            help="Trip slug to clean (default: brock-trip-2026)",
        )

    def handle(self, *args, **options):
        trip = Trip.objects.filter(slug=options["trip_slug"]).first()
        if not trip:
            self.stdout.write(self.style.WARNING(f"No trip with slug {options['trip_slug']!r}."))
            return

        lists = TaskList.objects.filter(trip=trip, name__istartswith="Smoke")
        list_count = lists.count()
        lists.delete()

        notes = InfoPage.objects.filter(trip=trip, title__istartswith="Smoke")
        note_count = notes.count()
        notes.delete()

        events = Event.objects.filter(trip=trip, name__istartswith="Smoke")
        event_count = events.count()
        events.delete()

        total = list_count + note_count + event_count
        if not total:
            self.stdout.write("No smoke artifacts found.")
            return
        self.stdout.write(self.style.SUCCESS(
            f"Removed {list_count} list(s), {note_count} note(s), {event_count} event(s)."
        ))
