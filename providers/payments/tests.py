from django.test import SimpleTestCase

from .base import get_payment_provider


class GetPaymentProviderTests(SimpleTestCase):
    def test_raises_for_unknown_provider(self):
        with self.settings(PAYMENT_PROVIDER="unknown"):
            with self.assertRaises(ValueError):
                get_payment_provider()

    # "mock"/"mercadopago" happy paths are tested once those providers exist
    # (MockPaymentProvider next, MercadoPagoPaymentProvider later).
