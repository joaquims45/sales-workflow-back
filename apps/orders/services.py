"""CheckoutService (ARCHITECTURE.md §17/§49).

Sales Workflow -> CheckoutAgent -> CheckoutService -> PaymentProvider ->
External Gateway. This is the only place an Order/Checkout gets created —
never from an agent, the LLM, or Jev directly. Price, stock and totals are
always re-read from Postgres here, never trusted from conversation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.catalog.models import Product
from events.bus import emit_event
from providers.payments.base import CheckoutResult, get_payment_provider

from .models import Order, OrderItem

if TYPE_CHECKING:
    from apps.conversations.models import Conversation
    from apps.customers.models import Customer


class ProductUnavailable(Exception):
    pass


class InsufficientStock(Exception):
    pass


@dataclass
class CheckoutOutcome:
    order: Order
    checkout_result: CheckoutResult


def create_checkout_for_product(
    product_id: int,
    conversation: "Conversation | None" = None,
    customer: "Customer | None" = None,
    quantity: int = 1,
) -> CheckoutOutcome:
    """SELECT_PRODUCT -> VALIDATE_PRODUCT -> VALIDATE_CURRENT_PRICE ->
    VALIDATE_STOCK -> CREATE_ORDER -> PaymentProvider -> CREATE_CHECKOUT."""

    product = Product.objects.filter(pk=product_id, is_active=True).first()
    if product is None:
        raise ProductUnavailable(f"Product {product_id} is not available.")

    if product.stock < quantity:
        raise InsufficientStock(f"Not enough stock for product {product_id}.")

    order = Order.objects.create(
        customer=customer,
        conversation=conversation,
        total=product.price * quantity,
        status=Order.Status.PENDING,
    )
    OrderItem.objects.create(order=order, product=product, quantity=quantity, unit_price=product.price)

    if conversation is not None:
        emit_event(conversation, "order.created", {"order_id": order.id, "total": str(order.total)})

    checkout_result = get_payment_provider().create_checkout(order)

    if conversation is not None:
        emit_event(
            conversation,
            "checkout.created",
            {
                "order_id": order.id,
                "checkout_url": checkout_result.checkout_url,
                "provider": checkout_result.provider,
            },
        )

    return CheckoutOutcome(order=order, checkout_result=checkout_result)
