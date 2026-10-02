"""
Django signals for automatic embedding indexing.

When an Application is created, updated, or has its categories changed,
a background thread is spawned to compute and store the embedding.

Why background thread instead of synchronous?
- The Gemini API call takes ~200-500ms
- If the API is down or rate-limited, the app still saves successfully
- The developer's publish form submission is never blocked or crashed

The app is marked with embedding=None until indexing succeeds.
It's still visible in the regular catalog, just not discoverable via AI search.
"""

import logging
import threading

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from marketplace.models import Application

logger = logging.getLogger(__name__)


def _compute_and_store_embedding(app_pk: int):
    """
    Background thread target: fetches the app, generates its embedding,
    and stores it. All errors are caught and logged.
    """
    try:
        # Import here to avoid circular imports
        from marketplace.services.embedding import generate_app_embedding

        app = Application.objects.prefetch_related("categories", "os").get(pk=app_pk)
        embedding = generate_app_embedding(app)

        # Use .update() instead of .save() to:
        # 1. Avoid re-triggering the post_save signal (infinite loop)
        # 2. Only touch the embedding column, not the entire row
        Application.objects.filter(pk=app_pk).update(embedding=embedding)

        logger.info(
            f"Successfully indexed embedding for app '{app.app_name}' (pk={app_pk})"
        )
    except Exception:
        # Log the full traceback but don't crash
        # The app is still saved — it's just not searchable via AI
        # until the next successful indexing attempt
        logger.exception(
            f"Failed to compute embedding for app pk={app_pk}. "
            f"The app is saved but won't appear in AI search results "
            f"until embedding is generated (e.g., on next save or via "
            f"'python manage.py backfill_embeddings')."
        )
    finally:
        from django.db import connection
        connection.close()


@receiver(post_save, sender=Application)
def index_application_on_save(sender, instance, **kwargs):
    """
    Triggered when Application.save() is called (create or update).

    Spawns a daemon thread to compute the embedding asynchronously.
    Daemon threads are automatically killed when the main process exits,
    so they won't keep the Django dev server hanging.
    """
    threading.Thread(
        target=_compute_and_store_embedding,
        args=(instance.pk,),
        daemon=True,
    ).start()


@receiver(m2m_changed, sender=Application.categories.through)
def index_application_on_category_change(sender, instance, action, **kwargs):
    """
    Triggered when categories are added/removed from an Application.

    M2M changes don't trigger post_save, so we need a separate signal.
    We only react to post_add/post_remove/post_clear (after the DB change),
    not pre_* (before the change is committed).
    """
    if action in ("post_add", "post_remove", "post_clear"):
        threading.Thread(
            target=_compute_and_store_embedding,
            args=(instance.pk,),
            daemon=True,
        ).start()
