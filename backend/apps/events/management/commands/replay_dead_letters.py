from django.core.management.base import BaseCommand

from apps.events.transport import get_publisher
from apps.events.consumer import replay_dead_letters


class Command(BaseCommand):
    help = "Re-send unresolved dead-lettered events (run this after fixing what made them fail)."

    def handle(self, *args, **options):
        count = replay_dead_letters(get_publisher)
        self.stdout.write(self.style.SUCCESS(f"Replayed {count} dead-lettered event(s)."))
