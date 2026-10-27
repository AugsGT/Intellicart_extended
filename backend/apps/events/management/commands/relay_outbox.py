import time

from django.core.management.base import BaseCommand

from apps.events.relay import relay_pending


class Command(BaseCommand):
    help = "Send pending outbox events to RabbitMQ (once, or every few seconds with --loop). Celery beat does the same job."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="keep running, one pass every --interval seconds")
        parser.add_argument("--interval", type=float, default=3.0)

    def handle(self, *args, **options):
        while True:
            result = relay_pending()
            if result["sent"] or result["failed"]:
                self.stdout.write(f"sent={result['sent']} failed={result['failed']}")
            if not options["loop"]:
                return
            time.sleep(options["interval"])
