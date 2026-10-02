from unittest.mock import patch
from rest_framework import status

from marketplace.models import (
    CustomUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
)
from marketplace.tests.base import BaseAPITestCase


class IntentSearchAPITests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dev_user = CustomUser.objects.create_user(
            username="p4_dev",
            email="p4dev@example.com",
            password="Password123!",
            first_name="P4",
            last_name="Dev",
            country="US",
            user_type="developer",
        )
        cls.developer = Developer.objects.create(
            user=cls.dev_user,
            developer_alias="p4_alias",
            payment_method="upi",
            payment_details="p4@upi",
        )
        cls.category = Category.objects.create(
            category_name="Productivity", description="Productivity Apps"
        )
        cls.os = OperatingSystem.objects.create(os_name="Linux")

    # Scenario 1: Empty query
    def test_scenario_1_empty_query(self):
        # Empty string
        res = self.client.post("/api/search/", {"query": ""}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res.data)
        self.assertIn("Please enter a valid search query", res.data["error"])
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["explanation"])

        # Whitespace only
        res_ws = self.client.post("/api/search/", {"query": "   "}, format="json")
        self.assertEqual(res_ws.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res_ws.data)

        # Missing query key
        res_empty = self.client.post("/api/search/", {}, format="json")
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res_empty.data)

        # Exceeds max length (300 chars)
        res_toolong = self.client.post("/api/search/", {"query": "a" * 301}, format="json")
        self.assertEqual(res_toolong.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res_toolong.data)

    # Scenario 2: Empty catalog (0 apps in DB)
    def test_scenario_2_empty_catalog(self):
        Application.objects.all().delete()
        res = self.client.post(
            "/api/search/", {"query": "looking for music player"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["explanation"])
        self.assertIn("no apps in the marketplace yet", res.data["error"].lower())

    # Scenario 3: No indexed apps (apps exist but none have embeddings)
    def test_scenario_3_no_indexed_apps(self):
        app = Application.objects.create(
            developer=self.developer,
            app_name="UnindexedApp",
            app_description="Description",
            price=0.0,
            embedding=None,
        )
        Application.objects.filter(pk=app.pk).update(embedding=None)

        res = self.client.post(
            "/api/search/", {"query": "looking for calculator"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["explanation"])
        self.assertIn("still setting up", res.data["error"].lower())

    # Scenario 4: Embedding API down
    @patch("marketplace.api.search.generate_query_embedding")
    def test_scenario_4_embedding_api_down(self, mock_embed):
        dummy_vector = [0.1] * 768
        app = Application.objects.create(
            developer=self.developer,
            app_name="IndexedApp",
            app_description="Description",
            price=0.0,
            embedding=dummy_vector,
        )
        Application.objects.filter(pk=app.pk).update(embedding=dummy_vector)

        mock_embed.side_effect = Exception("Gemini 503 Service Unavailable")

        res = self.client.post(
            "/api/search/", {"query": "any valid query"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["explanation"])
        self.assertIn("temporarily unavailable", res.data["error"])

    # Scenario 5: No relevant results
    @patch("marketplace.api.search.generate_query_embedding")
    def test_scenario_5_no_relevant_results(self, mock_embed):
        app_vector = [0.0] * 768
        app_vector[0] = 1.0

        query_vector = [0.0] * 768
        query_vector[1] = 1.0

        mock_embed.return_value = query_vector

        app = Application.objects.create(
            developer=self.developer,
            app_name="DissimilarApp",
            app_description="Description",
            price=0.0,
            embedding=app_vector,
        )
        Application.objects.filter(pk=app.pk).update(embedding=app_vector)

        res = self.client.post(
            "/api/search/", {"query": "gibberish or unrelated topic"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["error"])
        self.assertIn("couldn't find apps", res.data["explanation"].lower())

    # Scenario 6: LLM down (graceful degradation)
    @patch("marketplace.api.search.generate_explanation")
    @patch("marketplace.api.search.generate_query_embedding")
    def test_scenario_6_llm_down_graceful_degradation(self, mock_embed, mock_explain):
        matched_vector = [0.1] * 768
        mock_embed.return_value = matched_vector

        app = Application.objects.create(
            developer=self.developer,
            app_name="RelevantApp",
            app_description="A productivity planner",
            price=0.0,
            embedding=matched_vector,
        )
        app.categories.add(self.category)
        app.os.add(self.os)
        Application.objects.filter(pk=app.pk).update(embedding=matched_vector)

        mock_explain.side_effect = Exception("LLM rate limit / 500 error")

        res = self.client.post(
            "/api/search/", {"query": "productivity planner"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["apps"]), 1)
        self.assertEqual(res.data["apps"][0]["app_name"], "RelevantApp")
        self.assertIsNone(res.data["explanation"])
        self.assertIsNone(res.data["error"])

    # Success scenario: both embedding and LLM succeed
    @patch("marketplace.api.search.generate_explanation")
    @patch("marketplace.api.search.generate_query_embedding")
    def test_search_success_with_explanation(self, mock_embed, mock_explain):
        matched_vector = [0.1] * 768
        mock_embed.return_value = matched_vector
        mock_explain.return_value = "We found RelevantApp which helps you plan tasks."

        app = Application.objects.create(
            developer=self.developer,
            app_name="RelevantApp",
            app_description="A productivity planner",
            price=4.99,
            embedding=matched_vector,
        )
        app.categories.add(self.category)
        app.os.add(self.os)
        Application.objects.filter(pk=app.pk).update(embedding=matched_vector)

        res = self.client.post(
            "/api/search/", {"query": "productivity planner"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["apps"]), 1)
        self.assertEqual(res.data["apps"][0]["app_name"], "RelevantApp")
        self.assertEqual(
            res.data["explanation"],
            "We found RelevantApp which helps you plan tasks.",
        )
        self.assertIsNone(res.data["error"])

    # Scenario 7: Rate limiting configuration verification
    def test_scenario_7_rate_limit_throttle_configured(self):
        from marketplace.api.search import intent_search
        from rest_framework.throttling import AnonRateThrottle

        self.assertTrue(
            hasattr(intent_search, "cls")
            and AnonRateThrottle in intent_search.cls.throttle_classes
        )
