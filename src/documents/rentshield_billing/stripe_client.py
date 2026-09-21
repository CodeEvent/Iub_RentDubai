# Thin wrapper around the `stripe` package -- only the two calls this
# app actually needs (create a Checkout Session, verify a webhook
# signature), same "small client module, no SDK abstraction beyond
# what's used" style as documents/rentshield/esign/docuseal_client.py.
# Stripe's own docs for these two calls:
# https://docs.stripe.com/api/checkout/sessions/create
# https://docs.stripe.com/webhooks#verify-events
from __future__ import annotations

import stripe


def create_checkout_session(*, order, success_url: str, cancel_url: str, customer_email: str | None = None) -> str:
    """Creates a Stripe Checkout Session for `order` (a
    documents.rentshield_billing.models.Order) and returns its hosted
    checkout URL. Amount is AED, converted to fils (Stripe's smallest-
    unit requirement) -- `unit_amount` is always an integer count of
    the currency's smallest unit, never a decimal AED value."""
    from django.conf import settings

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "aed",
                    "unit_amount": order.amount_aed * 100,
                    "product_data": {"name": f"RentShield notice generation (Order #{order.pk})"},
                },
                "quantity": 1,
            },
        ],
        customer_email=customer_email or None,
        client_reference_id=str(order.pk),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"order_id": str(order.pk)},
    )
    return session.url


def verify_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    """Verifies `payload` was genuinely sent by Stripe (not spoofed) --
    raises stripe.error.SignatureVerificationError on a bad/missing
    signature, which the calling view turns into a 400. Never trust an
    unverified webhook body."""
    from django.conf import settings

    return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
