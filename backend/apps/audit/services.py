from apps.audit.models import AuditLog

# Actions recorded by the application (kept in one place so the UI filter and the tests agree).
ACTIONS = {
    "USER_UPDATED": "Account details or role changed by an administrator",
    "USER_DEACTIVATED": "Account deactivated by an administrator",
    "LOGIN_FAILED": "Failed login attempt",
    "STAFF_LOGIN": "Staff member logged in",
    "PRODUCT_CREATED": "Product created",
    "PRODUCT_UPDATED": "Product edited",
    "PRODUCT_ARCHIVED": "Product archived",
    "CATEGORY_CREATED": "Category created",
    "CATEGORY_UPDATED": "Category edited",
    "CATEGORY_DELETED": "Category deleted",
    "ATTRIBUTE_CREATED": "Product specification field created",
    "STOCK_RESTOCKED": "Stock added by an administrator",
    "STOCK_ADJUSTED": "Stock corrected by an administrator",
    "ORDER_STATUS_CHANGED": "Order status changed",
    "ORDER_CANCELLED": "Order cancelled",
    "ALERT_RESOLVED": "Alert resolved",
    "OPS_ASSISTANT_QUERY": "Question put to the operations assistant",
}

IGNORED_FIELDS = {"password", "token", "refresh", "access", "card_number"}


def client_ip(request) -> str | None:
    """The caller's address. Behind a trusted reverse proxy set TRUST_PROXY_HEADERS so the
    first X-Forwarded-For entry is used; otherwise the socket address is the only thing believed."""
    if request is None:
        return None
    from django.conf import settings

    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR") or None


def clean(details: dict | None) -> dict:
    """Drop anything secret-looking before it is stored."""
    return {k: v for k, v in (details or {}).items() if k not in IGNORED_FIELDS}


def record(request, action: str, summary: str, *, actor=None, entity_type: str = "", entity_id="", details: dict | None = None) -> AuditLog:
    """Write one audit entry. `actor` defaults to the authenticated user of the request."""
    if actor is None and request is not None and getattr(request, "user", None) is not None and request.user.is_authenticated:
        actor = request.user
    return AuditLog.objects.create(
        actor=actor,
        actor_label=getattr(actor, "email", "") or "",
        actor_role=getattr(actor, "role", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id != "" else "",
        summary=summary[:300],
        details=clean(details),
        ip_address=client_ip(request),
    )


def changed_fields(before: dict, after: dict) -> dict:
    """{"price": {"from": "10", "to": "12"}} for the fields that differ."""
    return {key: {"from": str(before[key]), "to": str(after[key])} for key in after if str(before.get(key)) != str(after[key])}
