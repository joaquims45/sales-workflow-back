"""MockPaymentProvider (ARCHITECTURE.md §40) — the default payment provider
in every environment. Simulates a gateway with zero external dependencies:
`create_checkout` creates a PENDING Payment and a fake checkout URL; the
dev-only endpoints in apps.payments.views (`/mock-checkout/<ref>/approve|
reject/`) simulate what a real webhook would otherwise do.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Mapping

from apps.payments.models import Checkout, Payment

from .base import CheckoutResult, NormalizedStatus, WebhookResult

if TYPE_CHECKING:
    from apps.orders.models import Order


class MockPaymentProvider:
    name = "mock"

    def create_checkout(self, order: "Order") -> CheckoutResult:
        external_reference = str(uuid.uuid4())

        checkout = Checkout.objects.create(
            order=order,
            provider=self.name,
            external_reference=external_reference,
            checkout_url=f"/mock-checkout/{external_reference}/",
        )
        payment = Payment.objects.create(
            checkout=checkout,
            provider_payment_id=external_reference,
            status=Payment.Status.PENDING,
            amount=order.total,
        )

        return CheckoutResult(
            payment_id=str(payment.id),
            status=payment.status,
            checkout_url=checkout.checkout_url,
            provider=self.name,
            external_reference=external_reference,
            metadata={},
        )

    def get_payment_status(self, payment: Payment) -> NormalizedStatus:
        return payment.status

    def process_webhook(self, raw_payload: Any, headers: Mapping[str, str]) -> WebhookResult:
        # No real gateway, so no webhooks — status changes happen through
        # the mock-checkout approve/reject endpoints instead.
        raise NotImplementedError(
            "MockPaymentProvider has no webhooks; use the /mock-checkout/<ref>/approve|reject/ endpoints."
        )
