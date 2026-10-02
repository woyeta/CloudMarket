import time
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connections

from marketplace.models import (
    CustomUser,
    Developer,
    Category,
    Application,
)
from marketplace.signals import _compute_and_store_embedding


class SignalIndexingLiveTests(TransactionTestCase):
    """
    Uses TransactionTestCase so database commits from the main thread
    are visible to the asynchronous worker thread.
    """

    def setUp(self):
        self.dev_user = CustomUser.objects.create_user(
            username="sig_dev",
            email="sigdev@example.com",
            password="Password123!",
            first_name="Sig",
            last_name="Dev",
            country="US",
            user_type="developer",
        )
        self.developer = Developer.objects.create(
            user=self.dev_user,
            developer_alias="sig_dev_alias",
            payment_method="upi",
            payment_details="sig@upi",
        )
        self.category = Category.objects.create(
            category_name="Games", description="Games Category"
        )

    @override_settings(GEMINI_API_KEY="test-api-key")
    @patch("marketplace.services.embedding.generate_app_embedding")
    def test_signals_index_on_create_and_category_change(self, mock_generate_embedding):
        dummy_vector = [0.5] * 768
        mock_generate_embedding.return_value = dummy_vector

        # Create app -> should trigger post_save signal
        app = Application.objects.create(
            developer=self.developer,
            app_name="SignalApp",
            app_description="Testing signal automation.",
            price=0.0,
        )

        for _ in range(30):
            app.refresh_from_db()
            if app.embedding is not None:
                break
            time.sleep(0.1)

        self.assertIsNotNone(app.embedding)
        self.assertEqual(len(app.embedding), 768)

        # Test m2m_changed signal
        dummy_vector_2 = [0.7] * 768
        mock_generate_embedding.return_value = dummy_vector_2

        app.categories.add(self.category)

        for _ in range(30):
            app.refresh_from_db()
            if app.embedding and abs(app.embedding[0] - 0.7) < 1e-4:
                break
            time.sleep(0.1)

        self.assertIsNotNone(app.embedding)
        self.assertAlmostEqual(app.embedding[0], 0.7, places=4)


class SignalErrorHandlingTests(TestCase):

    def setUp(self):
        self.dev_user = CustomUser.objects.create_user(
            username="p4_sig_dev",
            email="p4sig@example.com",
            password="Password123!",
            first_name="P4",
            last_name="Sig",
            country="US",
            user_type="developer",
        )
        self.developer = Developer.objects.create(
            user=self.dev_user,
            developer_alias="p4_sig_alias",
            payment_method="upi",
            payment_details="p4sig@upi",
        )

    # Scenario 9: Embedding API down during indexing (signal handler)
    @patch("marketplace.signals.index_application_on_save")
    @patch("marketplace.services.embedding.generate_app_embedding")
    def test_scenario_9_signal_embedding_api_down(
        self, mock_generate_embedding, mock_signal
    ):
        mock_generate_embedding.side_effect = Exception("Embedding API down")

        app = Application.objects.create(
            developer=self.developer,
            app_name="SavedWithoutEmbeddingApp",
            app_description="This app should save even if embedding generation fails.",
            price=0.0,
        )

        # Call worker synchronously to verify error handling without race condition
        with self.assertLogs("marketplace.signals", level="ERROR") as cm:
            _compute_and_store_embedding(app.pk)

        app.refresh_from_db()
        self.assertIsNone(app.embedding)
        self.assertTrue(
            any("Failed to compute embedding" in msg for msg in cm.output)
        )
