from django.db import models


class Intervention(models.Model):
    """One automated customer-recovery decision, win or no-op: what the engine
    decided, which rule fired, the signals behind it, and what happened next.
    This is the audit trail the operations console shows."""

    class Status(models.TextChoices):
        SENT = "SENT", "Sent"            # shown to the customer
        LOGGED = "LOGGED", "Logged"      # decided to do nothing
        DISMISSED = "DISMISSED", "Dismissed"

    class Action(models.TextChoices):
        REMINDER = "REMINDER", "Cart reminder"
        CHECKOUT_REMINDER = "CHECKOUT_REMINDER", "Checkout reminder"
        STOCK_ALTERNATIVE = "STOCK_ALTERNATIVE", "Low-stock alternative"
        BACK_IN_STOCK_ALERT = "BACK_IN_STOCK_ALERT", "Back in stock"
        NO_ACTION = "NO_ACTION", "No action"

    user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    trigger_event_type = models.CharField(max_length=50)
    trigger_event_id = models.CharField(max_length=36, db_index=True)
    cart_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    rule = models.CharField(max_length=50)
    signals = models.JSONField(default=dict)
    message = models.CharField(max_length=300, blank=True)
    message_source = models.CharField(max_length=10, default="template")  # "llm" or "template"
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    clicked_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, blank=True)  # RECOVERED once the customer buys
    outcome_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
