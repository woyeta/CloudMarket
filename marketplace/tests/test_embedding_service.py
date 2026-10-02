import io
from unittest.mock import MagicMock, patch
from django.test import override_settings
from django.core.management import call_command

from marketplace.models import (
    CustomUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
)
from marketplace.services import embedding as embedding_service
from marketplace.tests.base import BaseTestCase


class EmbeddingServiceTests(BaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dev_user = CustomUser.objects.create_user(
            username="test_dev",
            email="dev@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="User",
            country="US",
            user_type="developer",
        )
        cls.developer = Developer.objects.create(
            user=cls.dev_user,
            developer_alias="test_dev_alias",
            payment_method="upi",
            payment_details="dev@upi",
        )
        cls.category1 = Category.objects.create(
            category_name="Music", description="Music Apps"
        )
        cls.category2 = Category.objects.create(
            category_name="Education", description="Learning Apps"
        )
        cls.os1 = OperatingSystem.objects.create(os_name="Android")
        cls.os2 = OperatingSystem.objects.create(os_name="iOS")

    def setUp(self):
        embedding_service._client = None

    def tearDown(self):
        embedding_service._client = None

    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key_raises_value_error(self):
        embedding_service._client = None
        with self.assertRaises(ValueError) as ctx:
            embedding_service._get_client()
        self.assertIn("GEMINI_API_KEY is not set", str(ctx.exception))

    @override_settings(GEMINI_API_KEY="test-api-key")
    @patch("marketplace.services.embedding.genai.Client")
    def test_generate_query_embedding_format(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        dummy_vector = [0.1] * 768
        mock_result = MagicMock()
        mock_result.embeddings = [MagicMock(values=dummy_vector)]
        mock_client.models.embed_content.return_value = mock_result

        query = "learn guitar as a beginner"
        result = embedding_service.generate_query_embedding(query)

        self.assertEqual(len(result), 768)
        self.assertEqual(result, dummy_vector)

        mock_client.models.embed_content.assert_called_once()
        call_kwargs = mock_client.models.embed_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-embedding-2")
        self.assertEqual(
            call_kwargs["contents"],
            "task: search result | query: learn guitar as a beginner",
        )
        self.assertEqual(call_kwargs["config"].output_dimensionality, 768)

    @override_settings(GEMINI_API_KEY="test-api-key")
    @patch("marketplace.services.embedding.genai.Client")
    def test_generate_app_embedding_format(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        dummy_vector = [0.2] * 768
        mock_result = MagicMock()
        mock_result.embeddings = [MagicMock(values=dummy_vector)]
        mock_client.models.embed_content.return_value = mock_result

        app = Application.objects.create(
            developer=self.developer,
            app_name="GuitarPro",
            app_description="Learn chords and scales easily.",
            price=4.99,
        )
        app.categories.add(self.category1, self.category2)
        app.os.add(self.os1, self.os2)

        result = embedding_service.generate_app_embedding(app)

        self.assertEqual(len(result), 768)
        self.assertEqual(result, dummy_vector)

        mock_client.models.embed_content.assert_called_once()
        call_kwargs = mock_client.models.embed_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-embedding-2")
        contents = call_kwargs["contents"]
        self.assertIn("title: GuitarPro", contents)
        self.assertIn("text: Learn chords and scales easily.", contents)
        self.assertIn("Categories:", contents)
        self.assertIn("Music", contents)
        self.assertIn("Education", contents)
        self.assertIn("Compatible with:", contents)
        self.assertIn("Android", contents)
        self.assertIn("iOS", contents)
        self.assertEqual(call_kwargs["config"].output_dimensionality, 768)

    @override_settings(GEMINI_API_KEY="test-api-key")
    @patch("marketplace.services.embedding.generate_app_embedding")
    def test_backfill_embeddings_command(self, mock_generate_embedding):
        dummy_vector = [0.3] * 768
        mock_generate_embedding.return_value = dummy_vector

        app1 = Application.objects.create(
            developer=self.developer,
            app_name="Backfill1",
            app_description="First app to backfill.",
            price=1.0,
        )
        app2 = Application.objects.create(
            developer=self.developer,
            app_name="Backfill2",
            app_description="Second app to backfill.",
            price=2.0,
        )
        Application.objects.filter(pk__in=[app1.pk, app2.pk]).update(embedding=None)
        mock_generate_embedding.reset_mock()

        # Test dry-run
        out = io.StringIO()
        call_command("backfill_embeddings", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("Dry run complete", output)
        mock_generate_embedding.assert_not_called()

        # Test actual backfill
        out = io.StringIO()
        call_command("backfill_embeddings", stdout=out)
        output = out.getvalue()
        self.assertIn("Backfill complete", output)
        self.assertIn("Indexed: Backfill1", output)
        self.assertIn("Indexed: Backfill2", output)

        app1.refresh_from_db()
        app2.refresh_from_db()
        self.assertIsNotNone(app1.embedding)
        self.assertIsNotNone(app2.embedding)
