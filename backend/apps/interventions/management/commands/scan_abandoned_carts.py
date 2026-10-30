from django.core.management.base import BaseCommand

from apps.interventions.scanner import scan_abandoned_carts


class Command(BaseCommand):
    help = "Flag idle carts as abandoned (emits CART_ABANDONED). Celery beat runs the same job every minute."

    def handle(self, *args, **options):
        self.stdout.write(f"Flagged {scan_abandoned_carts()} cart(s).")
