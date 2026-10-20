from unittest.mock import MagicMock, patch

import fakeredis
import redis

from marketplace.models import Application, Developer, CustomUser
from marketplace.services import cache
from marketplace.tests.base import BaseAPITestCase, BaseTestCase


def unit_vector(index=0):
    vec = [0.0] * 768
    vec[index] = 1.0
    return vec


class CacheKeyTests(BaseTestCase):

    def test_normalize_query(self):
        self.assertEqual(cache.normalize_query("  Guitar\tLESSONS \n "), "guitar lessons")
        # NFKC folds compatibility characters (fullwidth letters here)
        self.assertEqual(cache.normalize_query("ＧＵＩＴＡＲ"), "guitar")

    def test_equivalent_queries_share_a_key(self):
        a = cache.embedding_key("  Guitar   LESSONS", "model-a", 768)
        b = cache.embedding_key("guitar lessons", "model-a", 768)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("emb:v1:"))

    def test_model_and_dims_change_the_key(self):
        base = cache.embedding_key("guitar", "model-a", 768)
        self.assertNotEqual(base, cache.embedding_key("guitar", "model-b", 768))
        self.assertNotEqual(base, cache.embedding_key("guitar", "model-a", 1536))

    def test_explanation_key_depends_on_result_set_not_order(self):
        a = cache.explanation_key("guitar", "llm", [3, 1, 2])
        self.assertEqual(a, cache.explanation_key("guitar", "llm", [1, 2, 3]))
        self.assertNotEqual(a, cache.explanation_key("guitar", "llm", [1, 2]))

    @patch("marketplace.services.cache._client")
    def test_embedding_round_trip_as_float32(self, mock_client):
        mock_client.return_value = fakeredis.FakeRedis()
        vec = [0.5, -0.25, 0.125]
        cache.set_embedding("k", vec, ttl=60)
        self.assertEqual(cache.get_embedding("k"), vec)
        self.assertIsNone(cache.get_embedding("missing"))

    @patch("marketplace.services.cache._client")
    def test_redis_errors_are_swallowed(self, mock_client):
        broken = MagicMock()
        broken.get.side_effect = redis.ConnectionError("down")
        broken.set.side_effect = redis.ConnectionError("down")
        mock_client.return_value = broken
        self.assertIsNone(cache.get_embedding("k"))
        cache.set_embedding("k", [1.0], ttl=60)  # must not raise

    def test_disabled_without_redis_url(self):
        self.assertIsNone(cache.get_embedding("k"))
        self.assertEqual(cache.ping(), "disabled")


class SearchCacheTests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        user = CustomUser.objects.create_user(
            username="cache_dev", email="cache_dev@example.com", password="Password123!",
            first_name="Cache", last_name="Dev", country="US", user_type="developer",
        )
        developer = Developer.objects.create(
            user=user, developer_alias="cache_alias", payment_method="upi", payment_details="c@upi",
        )
        app = Application.objects.create(
            developer=developer, app_name="GuitarTutor",
            app_description="Interactive guitar lessons for beginners.", price=0,
        )
        Application.objects.filter(pk=app.pk).update(embedding=unit_vector())

    def setUp(self):
        patcher = patch("marketplace.services.cache._client")
        self.addCleanup(patcher.stop)
        patcher.start().return_value = fakeredis.FakeRedis()

    def search(self, query):
        return self.client.post("/api/search/", {"query": query}, format="json")

    @patch("marketplace.api.search.generate_explanation", return_value="GuitarTutor teaches guitar.")
    @patch("marketplace.api.search.generate_query_embedding", return_value=unit_vector())
    def test_repeat_query_skips_both_gemini_calls(self, mock_embed, mock_explain):
        first = self.search("Learn guitar")
        second = self.search("  learn   GUITAR ")

        self.assertEqual(mock_embed.call_count, 1)
        self.assertEqual(mock_explain.call_count, 1)
        self.assertEqual(second.data["explanation"], "GuitarTutor teaches guitar.")
        self.assertEqual(second.data["apps"], first.data["apps"])
        self.assertIn('cache;dur=', second["Server-Timing"])
        self.assertIn('desc="hit"', second["Server-Timing"])
        self.assertNotIn("embed;dur", second["Server-Timing"])
        self.assertNotIn("llm;dur", second["Server-Timing"])

    @patch("marketplace.api.search.generate_explanation", return_value=None)
    @patch("marketplace.api.search.generate_query_embedding", return_value=unit_vector())
    def test_failed_explanation_is_not_cached(self, mock_embed, mock_explain):
        self.search("learn guitar")
        self.search("learn guitar")
        self.assertEqual(mock_explain.call_count, 2)

    @patch("marketplace.api.search.generate_explanation", return_value="Explained.")
    @patch("marketplace.api.search.generate_query_embedding", return_value=unit_vector())
    def test_cold_search_reports_every_stage(self, mock_embed, mock_explain):
        timing = self.search("learn guitar")["Server-Timing"]
        for stage in ("connect;dur=", "cache;dur=", "embed;dur=", "db;dur=", "llm;dur=", "total;dur="):
            self.assertIn(stage, timing)
        self.assertIn('desc="miss"', timing)

    @patch("marketplace.api.search.generate_explanation", return_value="Explained.")
    @patch("marketplace.api.search.generate_query_embedding", return_value=unit_vector())
    def test_search_works_when_redis_is_down(self, mock_embed, mock_explain):
        broken = MagicMock()
        broken.get.side_effect = redis.ConnectionError("down")
        broken.set.side_effect = redis.ConnectionError("down")
        with patch("marketplace.services.cache._client", return_value=broken):
            res = self.search("learn guitar")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["apps"]), 1)
        self.assertEqual(res.data["mode"], "semantic")
