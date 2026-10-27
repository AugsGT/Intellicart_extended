import logging
import time

from django.core.management.base import BaseCommand

from apps.events.consumer import run_consumer


class Command(BaseCommand):
    help = "Consume domain events from RabbitMQ: log them, run handlers, retry failures, dead-letter the rest."

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        while True:
            try:
                run_consumer()
                return
            except KeyboardInterrupt:
                return
            except Exception as error:  # broker down or connection lost: wait and reconnect
                self.stderr.write(f"Consumer stopped ({error}); reconnecting in 5 seconds")
                time.sleep(5)
