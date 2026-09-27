from django.db import models


class Checkout(models.Model):
    """The mechanism used to attempt a payment for an Order (ARCHITECTURE.md
    §19). An Order can have more than one Checkout (e.g. a first attempt
    expires and a second one is created) — this is 1:N on purpose.
    """

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="checkouts")
    provider = models.CharField(max_length=50)  # "mock", "mercadopago", ...
    external_reference = models.CharField(max_length=200, blank=True)
    checkout_url = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Checkout #{self.pk} ({self.provider}) for order #{self.order_id}"


class Payment(models.Model):
    """A single transaction/attempt within a Checkout (ARCHITECTURE.md §19).

    Status is always one of these normalized values, regardless of
    provider (§46) — a provider adapter translates its own vocabulary into
    this one, never the other way around.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    checkout = models.ForeignKey(Checkout, on_delete=models.CASCADE, related_name="payments")
    provider_payment_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Raw provider payload, kept for debugging — never read by domain logic.
    raw_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment #{self.pk} ({self.status}) for checkout #{self.checkout_id}"
