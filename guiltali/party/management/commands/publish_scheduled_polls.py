"""Publish scheduled polls whose opens_at time has passed."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from party.models import Poll, Post
from party.views import _publish_poll_to_feed, _schedule_next_daily_poll


class Command(BaseCommand):
    help = "Publish scheduled polls to the feed and queue daily repeats."

    def handle(self, *args, **options):
        now = timezone.now()
        pending = Poll.objects.filter(
            opens_at__isnull=False,
            opens_at__lte=now,
        ).select_related("trip", "author").prefetch_related("options")
        published = 0
        for poll in pending:
            if Post.objects.filter(poll=poll).exists():
                continue
            post = _publish_poll_to_feed(poll)
            if post:
                published += 1
                self.stdout.write(f"Published poll #{poll.id}: {poll.question[:60]}")
                _schedule_next_daily_poll(poll)
        if published:
            self.stdout.write(self.style.SUCCESS(f"Published {published} poll(s)."))
        else:
            self.stdout.write("No scheduled polls ready.")
