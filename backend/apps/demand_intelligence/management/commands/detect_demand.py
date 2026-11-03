from django.core.management.base import BaseCommand

from apps.demand_intelligence.detection import detect_demand_signals


class Command(BaseCommand):
    help = "Check demand for spikes and predicted stockouts and raise or close alerts. Celery beat runs this every 15 minutes."

    def handle(self, *args, **options):
        result = detect_demand_signals()
        self.stdout.write(f"spikes flagged: {result['spikes_flagged']}, stockout risks flagged: {result['stockout_risks_flagged']}")
