from django.test import SimpleTestCase

from .base import get_payment_provider
from .mock import MockPaymentProvider


class GetPaymentProviderTests(SimpleTestCase):
    def test_defaults_to_mock(self):
        with self.settings(PAYMENT_PROVIDER="mock"):
            provider = get_payment_provider()

        self.assertIsInstance(provider, MockPaymentProvider)

    def test_raises_for_unknown_provider(self):
        with self.settings(PAYMENT_PROVIDER="unknown"):
            with self.assertRaises(ValueError):
                get_payment_provider()

    # "mercadopago" happy path is tested once that provider exists.
