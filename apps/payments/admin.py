from django.contrib import admin

from .models import Checkout, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("provider_payment_id", "status", "amount", "raw_metadata", "created_at")


@admin.register(Checkout)
class CheckoutAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "provider", "external_reference", "created_at")
    list_filter = ("provider",)
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "checkout", "status", "amount", "created_at")
    list_filter = ("status",)
