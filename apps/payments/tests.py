from decimal import Decimal

from django.test import TestCase

from apps.orders.models import Order

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
