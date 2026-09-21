# The real, payment-gated path to generating a notice -- see README's
# dated Stripe/billing section. Mounted under the same documents/
# URL namespace as documents/rentshield_views.py (paperless/urls.py),
# not a separate API prefix, matching this project's existing
# convention for RentShield-specific endpoints.
from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield.pricing import calculate_total
from documents.rentshield.roles import CanManageNotices
from documents.rentshield_billing.models import Order
from documents.rentshield_views import validate_notice_fields

logger = logging.getLogger("paperless.rentshield")


def finalize_paid_order(order: Order) -> None:
    """Generates the real notice for a PAID/DEMO_PAID order and records
    the resulting Document's id on it. Called synchronously in the demo
    path (create_checkout_view, so the response can return the finished
    document_id directly) and from a Celery task in the real-Stripe path
    (documents.tasks.finalize_paid_notice_task, dispatched by the
    webhook -- generation shouldn't block the webhook response)."""
    from documents.rentshield.service import generate_and_consume

    document = generate_and_consume(order.fields, owner_id=order.owner_id, synchronous=True)
    order.document_id = document.id
    order.save(update_fields=["document_id"])


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanManageNotices])
def create_checkout_view(request):
    """POST /api/documents/notice/checkout/ -- same body
    create_notice_view takes. Creates an Order, then either:
      - STRIPE_SECRET_KEY configured: creates a real Stripe Checkout
        Session and returns its URL for the frontend to redirect to.
        The notice itself isn't generated yet -- stripe_webhook_view
        does that once Stripe confirms payment.
      - Not configured (demo mode): marks the order paid immediately
        and generates the notice synchronously, right here, returning
        the resulting document_id in the same response -- no real
        charge, no redirect, clearly recorded as Order.Status.DEMO_PAID
        so it's never mistaken for real revenue later.
    """
    fields, error = validate_notice_fields(request.data)
    if error:
        return error

    amount_aed = calculate_total(
        {
            "certified_esignature": fields["add_notarization"],
            "ai_review": fields["add_ai_review"],
            "legal_review": fields["add_legal_review"],
            "real_notarization": fields["add_real_notarization"],
        },
    )
    order = Order.objects.create(owner=request.user, fields=fields, amount_aed=amount_aed)

    if not settings.STRIPE_SECRET_KEY:
        order.status = Order.Status.DEMO_PAID
        from django.utils import timezone

        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at"])
        try:
            finalize_paid_order(order)
        except Exception as exc:  # noqa: BLE001 - surface a real error, don't leave the order silently stuck
            logger.exception("create_checkout_view: demo-mode generation failed for order %s: %s", order.pk, exc)
            order.status = Order.Status.FAILED
            order.save(update_fields=["status"])
            return Response({"error": f"Demo payment succeeded but notice generation failed: {exc}"}, status=502)
        return Response(
            {
                "order_id": order.pk,
                "demo": True,
                "checkout_url": None,
                "status": order.status,
                "document_id": order.document_id,
            },
        )

    from documents.rentshield_billing.stripe_client import create_checkout_session

    base_url = settings.RENTSHIELD_INTERNAL_URL
    try:
        checkout_url = create_checkout_session(
            order=order,
            success_url=f"{base_url}/notices?checkout_order_id={order.pk}",
            cancel_url=f"{base_url}/notice/new?checkout_canceled=1",
            customer_email=getattr(request.user, "email", None),
        )
    except Exception as exc:  # noqa: BLE001 - both providers failed pattern, surface why
        logger.exception("create_checkout_view: Stripe Checkout Session creation failed for order %s: %s", order.pk, exc)
        order.status = Order.Status.FAILED
        order.save(update_fields=["status"])
        return Response({"error": f"Could not start checkout: {exc}"}, status=502)

    return Response({"order_id": order.pk, "demo": False, "checkout_url": checkout_url, "status": order.status})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def checkout_status_view(request, order_id: int):
    """GET /api/documents/notice/checkout/<order_id>/status/ -- polled
    by the frontend after a real-Stripe redirect returns (the demo path
    never needs this; it gets document_id directly from
    create_checkout_view's own response)."""
    order = get_object_or_404(Order, id=order_id, owner=request.user)
    return Response({"status": order.status, "document_id": order.document_id})


@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook_view(request):
    """POST /api/documents/notice/stripe-webhook/ -- Stripe calls this
    server-to-server; deliberately AllowAny (no user session exists for
    Stripe's own request), same reasoning as
    documents/rentshield_views.py's analyze_uploaded_view. Trust comes
    from the signature check, not authentication -- an invalid/missing
    signature is rejected outright before anything else happens.
    """
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    from documents.rentshield_billing.stripe_client import verify_webhook_event

    try:
        event = verify_webhook_event(request.body, sig_header)
    except Exception as exc:  # noqa: BLE001 - reject anything that doesn't verify, don't leak why beyond a log
        logger.warning("stripe_webhook_view: signature verification failed: %s", exc)
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
        if not order_id:
            logger.warning("stripe_webhook_view: checkout.session.completed with no order_id in metadata")
            return HttpResponse(status=200)
        order = Order.objects.filter(id=order_id).first()
        if not order:
            logger.warning("stripe_webhook_view: no Order %s for completed checkout session", order_id)
            return HttpResponse(status=200)
        if order.status == Order.Status.PENDING:
            from django.utils import timezone

            order.status = Order.Status.PAID
            order.paid_at = timezone.now()
            order.stripe_checkout_session_id = session.get("id", "")
            order.save(update_fields=["status", "paid_at", "stripe_checkout_session_id"])

            from documents.tasks import finalize_paid_notice_task

            finalize_paid_notice_task.delay(order.id)

    return HttpResponse(status=200)
