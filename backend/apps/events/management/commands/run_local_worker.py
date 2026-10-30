import time

from django.core.management.base import BaseCommand

from apps.demand_intelligence.detection import detect_demand_signals
from apps.events.relay import relay_pending
from apps.interventions.scanner import scan_abandoned_carts


class Command(BaseCommand):
    help = (
        "Development stand-in for Celery beat: every few seconds send outbox events, once a minute scan for "
        "abandoned carts, and every 5 minutes check demand for spikes and stockouts. With EVENT_TRANSPORT=local this also processes events."
    )

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=2.0, help="seconds between relay passes")
        parser.add_argument("--scan-every", type=float, default=60.0, help="seconds between abandonment scans")
        parser.add_argument("--demand-every", type=float, default=300.0, help="seconds between demand checks")

    def handle(self, *args, **options):
        last_scan = last_demand = 0.0
        self.stdout.write("Local worker running (Ctrl+C to stop)")
        while True:
            result = relay_pending()
            if result["sent"] or result["failed"]:
                self.stdout.write(f"relay: sent={result['sent']} failed={result['failed']}")
            if time.monotonic() - last_scan >= options["scan_every"]:
                last_scan = time.monotonic()
                flagged = scan_abandoned_carts()
                if flagged:
                    self.stdout.write(f"scanner: flagged {flagged} abandoned cart(s)")
            if time.monotonic() - last_demand >= options["demand_every"]:
                last_demand = time.monotonic()
                found = detect_demand_signals()
                if found["spikes_flagged"] or found["stockout_risks_flagged"]:
                    self.stdout.write(f"demand: {found}")
            time.sleep(options["interval"])
