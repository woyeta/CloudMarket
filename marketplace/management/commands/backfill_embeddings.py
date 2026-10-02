"""
Management command to generate embeddings for all apps that don't have one.

Usage:
    python manage.py backfill_embeddings           # Index all unindexed apps
    python manage.py backfill_embeddings --all      # Re-index ALL apps (even already indexed)
    python manage.py backfill_embeddings --dry-run  # Show what would be indexed without doing it

Rate limiting:
    The Gemini free tier allows 1,500 requests/day.
    This command adds a 1-second delay between API calls to stay well within limits.
    For a catalog of 100 apps, the full backfill takes ~2 minutes.
"""

import time

from django.core.management.base import BaseCommand

from marketplace.models import Application
from marketplace.services.embedding import generate_app_embedding


class Command(BaseCommand):
    help = "Generate embeddings for all apps that don't have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Re-index ALL apps, even those that already have embeddings.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be indexed without actually calling the API.',
        )

    def handle(self, *args, **options):
        reindex_all = options['all']
        dry_run = options['dry_run']

        # Select apps to process
        if reindex_all:
            apps = Application.objects.all().prefetch_related('categories', 'os')
            self.stdout.write("Mode: Re-indexing ALL apps.")
        else:
            apps = (
                Application.objects
                .filter(embedding__isnull=True)
                .prefetch_related('categories', 'os')
            )
            self.stdout.write("Mode: Indexing apps without embeddings.")

        total = apps.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No apps to index. All done!"))
            return

        self.stdout.write(f"Found {total} app(s) to process.\n")

        if dry_run:
            for i, app in enumerate(apps, 1):
                has_embedding = app.embedding is not None
                status = "HAS embedding" if has_embedding else "NO embedding"
                self.stdout.write(f"  [{i}/{total}] {app.app_name} — {status}")
            self.stdout.write(self.style.WARNING("\nDry run complete. No API calls were made."))
            return

        succeeded = 0
        failed = 0

        for i, app in enumerate(apps, 1):
            try:
                embedding = generate_app_embedding(app)
                Application.objects.filter(pk=app.pk).update(embedding=embedding)
                self.stdout.write(
                    self.style.SUCCESS(f"  [{i}/{total}] [OK] Indexed: {app.app_name}")
                )
                succeeded += 1
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"  [{i}/{total}] [FAIL] FAILED: {app.app_name} — {e}")
                )
                failed += 1

            # Respect rate limits: 1,500 req/day ≈ ~1 req/sec is very safe
            if i < total:
                time.sleep(1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Backfill complete: {succeeded} succeeded, {failed} failed."))
