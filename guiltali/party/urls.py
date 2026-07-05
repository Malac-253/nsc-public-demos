from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.trips_home, name="trips_home"),
    path("trips/<int:trip_id>/choose/", views.choose_trip, name="choose_trip"),
    path("home/", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(template_name="party/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("itinerary/", views.itinerary, name="itinerary"),
    path("schedule/", views.schedule, name="schedule"),
    path("stay/", views.stay, name="stay"),
    path("experience/", views.experience, name="experience"),
    path("experience/edit/", views.trip_edit, name="trip_edit"),

    path("budget/", views.budget, name="budget"),
    path("budget/add/", views.budget_add, name="budget_add"),
    path("budget/confirm/", views.budget_confirm, name="budget_confirm"),
    path("budget/charts/", views.budget_charts, name="budget_charts"),
    path("budget/settle/", views.settle_screen, name="settle"),
    path("budget/receipt/", views.receipt, name="receipt_group"),
    path("budget/receipt/<int:member_id>/", views.receipt, name="receipt_member"),

    path("info/", views.info, name="info"),
    path("info/new/", views.info_new, name="info_new"),
    path("info/lists/new/", views.list_new, name="list_new"),
    path("info/lists/<int:list_id>/", views.list_detail, name="list_detail"),
    path("info/tools/", views.tools, name="tools"),
    path("info/<slug:slug>/", views.info_page, name="info_page"),

    path("feed/", views.feed, name="feed"),
    path("feed/new/", views.feed_new, name="feed_new"),
    path("feed/react/", views.react, name="react"),
    path("photos/", views.photos, name="photos"),
    path("polls/<int:poll_id>/", views.poll_detail, name="poll_detail"),

    path("party/", views.party, name="party"),
    path("settings/", views.settings_page, name="settings"),
]
