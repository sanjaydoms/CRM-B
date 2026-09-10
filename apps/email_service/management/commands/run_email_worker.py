import time
import logging
from django.core.management.base import BaseCommand
from apps.email_service.services.email_job_service import EmailJobService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Runs background worker polling Upstash Redis to process queued email jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Process currently queued jobs once and exit.',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=2,
            help='Poll interval in seconds when running in continuous mode (default: 2s).',
        )

    def handle(self, *args, **options):
        once_mode = options.get('once', False)
        interval = options.get('interval', 2)

        self.stdout.write(self.style.SUCCESS(f"Starting Email Queue Worker (once_mode={once_mode}, interval={interval}s)..."))

        while True:
            processed = 0
            while True:
                job_result = EmailJobService.process_next_queued_job()
                if not job_result:
                    break
                processed += 1
                job_id = job_result.get("job_id")
                sent_count = job_result.get("sent_count", 0)
                status = job_result.get("status")
                self.stdout.write(
                    self.style.SUCCESS(f"Processed email job {job_id}: status={status}, sent_count={sent_count}")
                )

            if once_mode:
                self.stdout.write(self.style.SUCCESS(f"Finished processing queued jobs (total={processed}). Exiting."))
                break

            time.sleep(interval)
