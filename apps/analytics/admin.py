from django.contrib import admin

from .models import WorkflowEvent


@admin.register(WorkflowEvent)
class WorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "event_type", "created_at")
    list_filter = ("event_type",)
    readonly_fields = ("conversation", "event_type", "payload", "created_at")
