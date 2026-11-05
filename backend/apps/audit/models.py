from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    pass


class AuditQuerySet(models.QuerySet):
    """The audit log can be added to, never edited or removed (not even in bulk)."""

    def update(self, **kwargs):
        raise AppendOnlyError("Audit log entries cannot be modified")

    def delete(self):
        raise AppendOnlyError("Audit log entries cannot be deleted")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AppendOnlyError("Audit log entries cannot be modified")


class AuditLog(models.Model):
    """Who did what, to which record, and when.

    `actor_label` keeps the email even if the account is later deactivated, so the
    trail stays readable. `details` holds a small, hand-picked summary of the change
    (never passwords, tokens or payment details).
    """

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    actor_label = models.CharField(max_length=255, blank=True)   # email at the time; empty for anonymous events
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=40, db_index=True)       # e.g. ORDER_STATUS_CHANGED
    entity_type = models.CharField(max_length=40, blank=True, db_index=True)
    entity_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=300)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError("Audit log entries cannot be modified")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit log entries cannot be deleted")
