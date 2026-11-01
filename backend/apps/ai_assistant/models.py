from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """A shopping conversation that belongs to one logged-in customer.

    `requirements` is what the advisor has understood so far (category, budget,
    priorities...), kept between messages so the customer never repeats themselves.
    `last_results` are the product ids last shown, in order, so "the second one"
    can be resolved. `pending_action` is an action waiting for the customer's
    confirmation (the assistant never acts without it).
    """

    class Kind(models.TextChoices):
        SHOPPING = "shopping", "Shopping advisor"
        OPERATIONS = "operations", "Operations assistant"

    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SHOPPING, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=100, blank=True)
    requirements = models.JSONField(default=dict)
    last_results = models.JSONField(default=list)
    pending_action = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Customer"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    # Structured extras for the UI: product cards, comparison table, pending action.
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
