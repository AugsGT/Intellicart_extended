from django.db import models


class IntentScore(models.Model):
    """One scoring run for a customer (append-only, so history is kept). `basis`
    stores the exact signal counts and weights used, so every score can be explained.
    A customer is a logged-in user_id and/or an anonymous browser session_key."""

    user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    score = models.PositiveIntegerField()
    tier = models.CharField(max_length=10, db_index=True)  # LOW / MEDIUM / HIGH
    basis = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
