from django.contrib import admin

from .models import Conversation, Message, SalesStateSnapshot


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "created_at")


class SalesStateSnapshotInline(admin.StackedInline):
    model = SalesStateSnapshot
    extra = 0
    readonly_fields = ("state", "updated_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "is_active", "created_at")
    list_filter = ("is_active",)
    inlines = [MessageInline, SalesStateSnapshotInline]
