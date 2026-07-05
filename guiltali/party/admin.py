from django.contrib import admin

from . import models


class MembershipInline(admin.TabularInline):
    model = models.Membership
    extra = 0


@admin.register(models.Party)
class PartyAdmin(admin.ModelAdmin):
    inlines = [MembershipInline]
    prepopulated_fields = {"slug": ("name",)}


class AttendanceInline(admin.TabularInline):
    model = models.Attendance
    extra = 0


class RoomInline(admin.TabularInline):
    model = models.Room
    extra = 0


@admin.register(models.Trip)
class TripAdmin(admin.ModelAdmin):
    inlines = [AttendanceInline, RoomInline]
    prepopulated_fields = {"slug": ("name",)}


class TaskItemInline(admin.TabularInline):
    model = models.TaskItem
    extra = 0


@admin.register(models.TaskList)
class TaskListAdmin(admin.ModelAdmin):
    inlines = [TaskItemInline]
    list_display = ("name", "kind", "trip")


class PollOptionInline(admin.TabularInline):
    model = models.PollOption
    extra = 0


@admin.register(models.Poll)
class PollAdmin(admin.ModelAdmin):
    inlines = [PollOptionInline]


class ExpenseShareInline(admin.TabularInline):
    model = models.ExpenseShare
    extra = 0


@admin.register(models.Expense)
class ExpenseAdmin(admin.ModelAdmin):
    inlines = [ExpenseShareInline]
    list_display = ("title", "amount", "payer", "split_method", "locked")


admin.site.register(models.Membership)
admin.site.register(models.Announcement)
admin.site.register(models.Settlement)
admin.site.register(models.Room)
admin.site.register(models.RoomClaim)
admin.site.register(models.Post)
admin.site.register(models.Comment)
