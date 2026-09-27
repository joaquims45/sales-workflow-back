"""Payment status transitions (ARCHITECTURE.md §42/§46).

The only place a Payment's status changes after creation. Keeps Order in
sync (an APPROVED payment confirms the order) and emits the normalized
`payment.*` event — regardless of which PaymentProvider caused the change,
so a webhook adapter and the mock-checkout dev endpoints both go through
here rather than poking `payment.status` directly.
"""

from __future__ import annotations

from apps.orders.models import Order
from events.bus import emit_event

from .models import Payment


def update_payment_status(payment: Payment, new_status: str) -> Payment:
    payment.status = new_status
    payment.save(update_fields=["status", "updated_at"])

    order = payment.checkout.order

    if new_status == Payment.Status.APPROVED and order.status != Order.Status.CONFIRMED:
        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])

    if order.conversation is not None:
        emit_event(
            order.conversation,
            f"payment.{new_status.lower()}",
            {"order_id": order.id, "payment_id": payment.id, "status": new_status},
        )

    return payment
