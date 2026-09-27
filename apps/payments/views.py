"""Dev-only endpoints that simulate a payment gateway for MockPaymentProvider
(ARCHITECTURE.md §40). Real providers (Mercado Pago, etc.) get their status
changes from actual webhooks instead — these views only exist because the
mock has no external gateway to call it back.
"""

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Checkout, Payment
from .services import update_payment_status


def _get_latest_payment(external_reference: str) -> Payment:
    checkout = get_object_or_404(Checkout, external_reference=external_reference, provider="mock")
    payment = checkout.payments.order_by("-created_at").first()
    if payment is None:
        raise Http404("No payment found for this checkout.")
    return payment


def mock_checkout_page(request, external_reference):
    payment = _get_latest_payment(external_reference)
    return JsonResponse(
        {
            "external_reference": external_reference,
            "status": payment.status,
            "amount": str(payment.amount),
        }
    )


@csrf_exempt
@require_POST
def approve_mock_payment(request, external_reference):
    payment = _get_latest_payment(external_reference)
    payment = update_payment_status(payment, Payment.Status.APPROVED)
    return JsonResponse({"status": payment.status})


@csrf_exempt
@require_POST
def reject_mock_payment(request, external_reference):
    payment = _get_latest_payment(external_reference)
    payment = update_payment_status(payment, Payment.Status.REJECTED)
    return JsonResponse({"status": payment.status})
