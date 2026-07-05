from .models import Announcement, Membership, Notification, Trip, UserProfile


def active_trip(request):
    """Attach the active trip + the requester's membership to every template."""
    trip = Trip.objects.filter(is_active=True).select_related("party").first()
    member = None
    announcements = []
    sounds_on = True
    unread_notif_count = 0
    recent_notifications = []
    if trip and request.user.is_authenticated:
        member = Membership.objects.filter(
            party=trip.party, user=request.user
        ).first()
        announcements = list(
            Announcement.objects.filter(trip=trip).select_related("author", "audience")[:5]
        )
        profile = UserProfile.objects.filter(user=request.user).first()
        if profile:
            sounds_on = profile.sounds_on
        if member:
            notifs_qs = Notification.objects.filter(recipient=member).select_related("actor")
            unread_notif_count = notifs_qs.filter(read_at__isnull=True).count()
            recent_notifications = list(notifs_qs[:8])
    return {
        "trip": trip,
        "me": member,
        "bar_announcements": announcements,
        "sounds_on": sounds_on,
        "unread_notif_count": unread_notif_count,
        "recent_notifications": recent_notifications,
    }
