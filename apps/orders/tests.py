from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product

from .models import Order, OrderItem


class OrderModelTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Notebooks", slug="notebooks")
        self.product = Product.objects.create(
            category=category,
            name="ASUS TUF Gaming A15",
            slug="asus-tuf-gaming-a15",
            description="Notebook gamer.",
            price="1400000.00",
            stock=5,
        )

    def test_order_defaults_to_pending(self):
        order = Order.objects.create(total=Decimal("1400000.00"))

        self.assertEqual(order.status, Order.Status.PENDING)

    def test_order_item_snapshots_unit_price(self):
        order = Order.objects.create(total=Decimal("1400000.00"))
        item = OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=self.product.price)

        self.product.price = Decimal("1500000.00")
        self.product.save()

        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("1400000.00"))

    def test_deleting_order_deletes_its_items(self):
        order = Order.objects.create(total=Decimal("1400000.00"))
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=self.product.price)

        order.delete()

        self.assertEqual(OrderItem.objects.count(), 0)
