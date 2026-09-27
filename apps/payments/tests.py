from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.orders.models import Order
from providers.payments.mock import MockPaymentProvider

from .models import Checkout, Payment


class CheckoutPaymentModelTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(total=Decimal("1400000.00"))

    def test_payment_defaults_to_pending(self):
        checkout = Checkout.objects.create(order=self.order, provider="mock")
        payment = Payment.objects.create(checkout=checkout, amount=self.order.total)

        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_order_can_have_multiple_checkouts(self):
        Checkout.objects.create(order=self.order, provider="mock")
        Checkout.objects.create(order=self.order, provider="mock")

        self.assertEqual(self.order.checkouts.count(), 2)

    def test_checkout_supports_retry_after_rejected_payment(self):
        checkout = Checkout.objects.create(order=self.order, provider="mock")
        Payment.objects.create(checkout=checkout, amount=self.order.total, status=Payment.Status.REJECTED)
        Payment.objects.create(checkout=checkout, amount=self.order.total, status=Payment.Status.APPROVED)

        statuses = list(checkout.payments.order_by("id").values_list("status", flat=True))
        self.assertEqual(statuses, [Payment.Status.REJECTED, Payment.Status.APPROVED])

    def test_deleting_order_deletes_checkouts_and_payments(self):
        checkout = Checkout.objects.create(order=self.order, provider="mock")
        Payment.objects.create(checkout=checkout, amount=self.order.total)

        self.order.delete()

        self.assertEqual(Checkout.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)


class MockPaymentProviderTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(total=Decimal("1400000.00"))
        self.provider = MockPaymentProvider()

    def test_create_checkout_creates_pending_payment(self):
        result = self.provider.create_checkout(self.order)

        self.assertEqual(result.status, Payment.Status.PENDING)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(Checkout.objects.filter(order=self.order).count(), 1)

        payment = Payment.objects.get(pk=result.payment_id)
        self.assertEqual(payment.amount, self.order.total)
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_get_payment_status_reflects_current_status(self):
        result = self.provider.create_checkout(self.order)
        payment = Payment.objects.get(pk=result.payment_id)

        self.assertEqual(self.provider.get_payment_status(payment), Payment.Status.PENDING)

        payment.status = Payment.Status.APPROVED
        payment.save(update_fields=["status"])
        self.assertEqual(self.provider.get_payment_status(payment), Payment.Status.APPROVED)

    def test_process_webhook_is_not_supported(self):
        with self.assertRaises(NotImplementedError):
            self.provider.process_webhook({}, {})


class MockCheckoutEndpointsTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(total=Decimal("1400000.00"))
        self.result = MockPaymentProvider().create_checkout(self.order)

    def test_checkout_page_reports_pending_status(self):
        url = reverse("mock-checkout-page", args=[self.result.external_reference])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Payment.Status.PENDING)

    def test_approve_endpoint_marks_payment_approved(self):
        url = reverse("mock-checkout-approve", args=[self.result.external_reference])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(pk=self.result.payment_id)
        self.assertEqual(payment.status, Payment.Status.APPROVED)

    def test_reject_endpoint_marks_payment_rejected(self):
        url = reverse("mock-checkout-reject", args=[self.result.external_reference])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(pk=self.result.payment_id)
        self.assertEqual(payment.status, Payment.Status.REJECTED)

    def test_approve_endpoint_rejects_get_requests(self):
        url = reverse("mock-checkout-approve", args=[self.result.external_reference])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_unknown_reference_returns_404(self):
        url = reverse("mock-checkout-page", args=["does-not-exist"])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
