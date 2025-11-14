from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status

from ...models.catalog import CatalogVariant, VariantAttribute
from ...models.customer import CustomerProfile, DeliverySettings, FulfillmentPreference, LoyaltyTier
from ...models.notification import NotificationEvent, NotificationTemplate
from ...models.order import (
    LineDiscount,
    OrderEnvelope,
    OrderLine,
    OrderPriority,
    OrderState,
    ShipmentLeg,
    StateTransition,
)
from ...models.payment import CaptureStatus, PaymentCapture, PaymentIntent, PaymentProvider
from ...models.shared import Address, AuditEvent, FulfillmentWindow, LocalizedText, Money

router = APIRouter()


def _now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _seed_orders() -> dict[str, OrderEnvelope]:
    created_at = _now()
    address = Address(
        line1="Fabriksgatan 12",
        city="Göteborg",
        postal_code="41123",
        country="SE",
    )
    customer = CustomerProfile(
        id=UUID("c5c9d58d-7ab1-4f87-a4cb-5fb46f7ee111"),
        email="astrid@example.com",
        primary_phone="+46700000000",
        shipping_address=address,
        loyalty_tier=LoyaltyTier.gold,
        created_at=created_at,
        updated_at=created_at,
        audit_trail=[
            AuditEvent(
                actor="ops@example.com",
                action="verified",
                at=created_at,
                metadata={"rule": "kyc"},
            )
        ],
    )

    light_variant = CatalogVariant(
        id=UUID("8f91b119-f779-415d-88d9-845d8f50c9d1"),
        sku="LIGHT-100",
        title="Portable light",
        attributes=[VariantAttribute(name="lumens", value="1000")],
        price=Money(amount=Decimal("129.00")),
        media=[],
    )

    intent = PaymentIntent(
        intent_id=UUID("a45cb4bd-7db7-4229-879c-37a3e777a2c1"),
        customer_id=customer.id,
        provider=PaymentProvider.stripe,
        amount=Money(amount=Decimal("228.00")),
        statement_descriptor="ASTRID-SHOP",
        created_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(hours=3),
        audit_trail=[],
    )

    capture = PaymentCapture(
        capture_id=UUID("ec8e6f3c-86a9-4c71-a34c-af0f07c21744"),
        intent_id=intent.intent_id,
        status=CaptureStatus.succeeded,
        requested_at=created_at + timedelta(minutes=5),
        captured_at=created_at + timedelta(minutes=6),
        amount=intent.amount,
    )

    notification = NotificationEvent(
        event_id=UUID("0f253f10-f7e5-4a3d-9465-784bc576a1f6"),
        channel="email",
        recipient=customer.email,
        template=NotificationTemplate(
            key="order.confirmed",
            subject=LocalizedText(locale="en-US", text="Order confirmed"),
            body=[LocalizedText(locale="en-US", text="Thanks for your purchase!")],
        ),
        sent_at=created_at + timedelta(minutes=1),
    )

    order = OrderEnvelope(
        order_id=UUID("df1c2d48-240d-4026-b4a0-341f77b2d220"),
        customer=customer,
        delivery=DeliverySettings(preference=FulfillmentPreference.delivery),
        items=[
            OrderLine(
                variant=light_variant,
                quantity=2,
                discounts=[LineDiscount(description="VIP", amount=Money(amount=Decimal("30.00")))],
            )
        ],
        payment_intent=intent,
        captures=[capture],
        state_history=[
        StateTransition(
            from_state=OrderState.draft,
            to_state=OrderState.confirmed,
            occurred_at=created_at,
        ),
        StateTransition(
            from_state=OrderState.confirmed,
            to_state=OrderState.allocated,
            occurred_at=created_at + timedelta(minutes=2),
        ),
        ],
        shipments=[
            ShipmentLeg(
                leg_id=UUID("20d9f1c9-5eb3-4f88-9a6b-8032fb3c0d09"),
                carrier="PostNord",
                tracking_code="PN12345678",
                destination=address,
                promised_window=FulfillmentWindow(
                    start=created_at + timedelta(days=1),
                    end=created_at + timedelta(days=3),
                ),
            )
        ],
        notifications=[notification],
        priority=OrderPriority.express,
        gift_message="Enjoy the northern lights!",
        created_at=created_at,
        updated_at=created_at + timedelta(minutes=10),
        audit_trail=[],
    )
    return {str(order.order_id): order}


_ORDERS = _seed_orders()


@router.get("/", response_model=list[OrderEnvelope])
def list_orders() -> list[OrderEnvelope]:
    return list(_ORDERS.values())


@router.get("/{order_id}", response_model=OrderEnvelope)
def get_order(order_id: UUID) -> OrderEnvelope:
    order = _ORDERS.get(str(order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/", response_model=OrderEnvelope, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderEnvelope) -> OrderEnvelope:
    if str(payload.order_id) in _ORDERS:
        raise HTTPException(status_code=409, detail="Order already exists")
    _ORDERS[str(payload.order_id)] = payload
    return payload


@router.post("/{order_id}/notifications", response_model=NotificationEvent)
def add_notification(order_id: UUID, notification: NotificationEvent) -> NotificationEvent:
    order = _ORDERS.get(str(order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order.notifications.append(notification)
    return notification


@router.post("/{order_id}/reroute", response_model=OrderEnvelope)
def reroute_delivery(order_id: UUID, destination: Address) -> OrderEnvelope:
    order = _ORDERS.get(str(order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    reroute_leg = ShipmentLeg(
        leg_id=uuid4(),
        carrier="BikeMates",
        tracking_code="CC" + uuid4().hex[:8].upper(),
        destination=destination,
        promised_window=FulfillmentWindow(
            start=_now() + timedelta(hours=2),
            end=_now() + timedelta(hours=4),
        ),
    )
    order.shipments.append(reroute_leg)
    order.updated_at = _now()
    return order
