from django.contrib import admin

from .models import AssistantConversation, AssistantDraft, AssistantMessage, AssistantUsageWindow


@admin.register(AssistantConversation)
class AssistantConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("token", "created_at", "updated_at")


@admin.register(AssistantMessage)
class AssistantMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "created_at")
    search_fields = ("content", "conversation__user__username")
    readonly_fields = ("created_at",)


@admin.register(AssistantDraft)
class AssistantDraftAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_task", "accepted_at", "created_at")
    search_fields = ("user__username", "payload")
    readonly_fields = ("token", "created_at", "accepted_at")


@admin.register(AssistantUsageWindow)
class AssistantUsageWindowAdmin(admin.ModelAdmin):
    list_display = ("user", "window_started", "count", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("updated_at",)
