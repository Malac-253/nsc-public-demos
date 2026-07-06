"""Remove feed posts (and their polls) except Malachi + Party AI Squire."""
from __future__ import annotations

from django.db.models import Q

from django.core.management.base import BaseCommand

from party.models import Membership, Poll, Post, Trip


class Command(BaseCommand):
    help = (
        "Delete Brock Trip feed posts from everyone except Malachi and the "
        "Party AI Squire. Safe to re-run."
    )

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

        keep = trip.party.memberships.filter(
            Q(user__username="malachi") | Q(is_ai=True),
        )
        posts = Post.objects.filter(trip=trip).exclude(author__in=keep)
        post_count = posts.count()
        posts.delete()

        polls = Poll.objects.filter(trip=trip).exclude(author__in=keep)
        poll_count = polls.count()
        polls.delete()

        kept = Post.objects.filter(trip=trip).count()
        if not post_count and not poll_count:
            self.stdout.write(f"Feed already clean ({kept} kept post(s)).")
            return
        self.stdout.write(self.style.SUCCESS(
            f"Removed {post_count} post(s) and {poll_count} poll(s). "
            f"{kept} post(s) kept (Malachi + Squire)."
        ))
