from unittest.mock import MagicMock, patch

from django.test import override_settings

from marketplace.models import Application, CustomUser, Developer
from marketplace.services import embedding as embedding_service
from marketplace.services import llm as llm_service
from marketplace.services.faults import InjectedFault, maybe_inject
from marketplace.services.keyword_search import keyword_search
from marketplace.tests.base import BaseAPITestCase, BaseTestCase


def unit_vector(index=0):
    vec = [0.0] * 768
    vec[index] = 1.0
    return vec


def make_developer(suffix):
    user = CustomUser.objects.create_user(
        username=f"fb_dev_{suffix}", email=f"fb_{suffix}@example.com", password="Password123!",
        first_name="Fb", last_name="Dev", country="US", user_type="developer",
    )
    return Developer.objects.create(
        user=user, developer_alias=f"fb_{suffix}", payment_method="upi", payment_details="fb@upi",
    )


class KeywordSearchTests(BaseTestCase):

    @classmethod
    def setUpTestData(cls):
        dev = make_developer("kw")
        Application.objects.create(
            developer=dev, app_name="ChordMaster",
            app_description="Practice guitar chords with interactive lessons.", price=0,
        )
        Application.objects.create(
            developer=dev, app_name="Guitar Studio",
            app_description="Record and mix your songs.", price=0,
        )
        Application.objects.create(
            developer=dev, app_name="BudgetBook",
            app_description="Track monthly spending and bills.", price=0,
        )

    def test_natural_language_query_matches_any_word(self):
        names = [a.app_name for a in keyword_search("I want to learn guitar as a beginner", 5)]
        self.assertIn("ChordMaster", names)
        self.assertIn("Guitar Studio", names)
        self.assertNotIn("BudgetBook", names)

    def test_name_match_ranks_above_description_match(self):
        names = [a.app_name for a in keyword_search("guitar", 5)]
        self.assertEqual(names[0], "Guitar Studio")

    def test_stemming(self):
        names = [a.app_name for a in keyword_search("tracking bill", 5)]
        self.assertEqual(names, ["BudgetBook"])

    def test_punctuation_only_and_operator_characters_are_safe(self):
        self.assertEqual(keyword_search("!!! ???", 5), [])
        # tsquery operators in user input must not raise a syntax error
        self.assertEqual([a.app_name for a in keyword_search("guitar & | ! ( ) :*", 5)][0], "Guitar Studio")


class SearchFallbackTests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        dev = make_developer("api")
        app = Application.objects.create(
            developer=dev, app_name="ChordMaster",
            app_description="Practice guitar chords with interactive lessons.", price=0,
        )
        Application.objects.filter(pk=app.pk).update(embedding=unit_vector())

    def search(self, query="learn guitar"):
        return self.client.post("/api/search/", {"query": query}, format="json")

    @patch("marketplace.api.search.generate_explanation")
    @patch("marketplace.api.search.generate_query_embedding")
    def test_embedding_failure_falls_back_to_keyword(self, mock_embed, mock_explain):
        mock_embed.side_effect = Exception("503 Service Unavailable")
        res = self.search("I want to learn guitar")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["mode"], "keyword")
        self.assertIsNone(res.data["error"])
        self.assertEqual(res.data["apps"][0]["app_name"], "ChordMaster")
        # Gemini is likely down: don't wait on the LLM as well
        mock_explain.assert_not_called()
        self.assertIn("keyword;dur=", res["Server-Timing"])

    @patch("marketplace.api.search.generate_explanation")
    @patch("marketplace.api.search.generate_query_embedding")
    def test_timeout_falls_back_to_keyword(self, mock_embed, mock_explain):
        mock_embed.side_effect = TimeoutError("timed out")
        res = self.search()
        self.assertEqual(res.data["mode"], "keyword")
        self.assertEqual(len(res.data["apps"]), 1)

    @patch("marketplace.api.search.generate_explanation", return_value="Explained.")
    @patch("marketplace.api.search.generate_query_embedding", return_value=unit_vector())
    def test_healthy_path_is_semantic(self, mock_embed, mock_explain):
        res = self.search()
        self.assertEqual(res.data["mode"], "semantic")
        self.assertEqual(res.data["explanation"], "Explained.")

    @patch("marketplace.api.search.generate_query_embedding")
    def test_keyword_no_match_returns_message_not_error(self, mock_embed):
        mock_embed.side_effect = Exception("down")
        res = self.search("spreadsheet invoices")
        self.assertEqual(res.data["apps"], [])
        self.assertIsNone(res.data["error"])
        self.assertIn("couldn't find apps", res.data["explanation"])

    @override_settings(ALLOW_FAULT_INJECTION=True, GEMINI_FAULT="fail")
    @patch("marketplace.api.search.generate_explanation")
    def test_injected_fault_end_to_end(self, mock_explain):
        # The real generate_query_embedding runs and hits the injected fault
        # before any network call.
        res = self.search()
        self.assertEqual(res.data["mode"], "keyword")
        self.assertEqual(len(res.data["apps"]), 1)


class FaultInjectionTests(BaseTestCase):

    @override_settings(ALLOW_FAULT_INJECTION=False, GEMINI_FAULT="fail")
    def test_ignored_unless_allowed(self):
        maybe_inject(2000)  # must not raise

    @override_settings(ALLOW_FAULT_INJECTION=True, GEMINI_FAULT="fail")
    def test_fail_mode(self):
        with self.assertRaises(InjectedFault):
            maybe_inject(2000)

    @override_settings(ALLOW_FAULT_INJECTION=True, GEMINI_FAULT="hang", GEMINI_FAULT_HANG_S=10.0)
    @patch("marketplace.services.faults.time.sleep")
    def test_hang_is_capped_at_the_timeout(self, mock_sleep):
        with self.assertRaises(TimeoutError):
            maybe_inject(2000)
        mock_sleep.assert_called_once_with(2.0)

    @override_settings(ALLOW_FAULT_INJECTION=True, GEMINI_FAULT="hang", GEMINI_FAULT_HANG_S=10.0)
    @patch("marketplace.services.faults.time.sleep")
    def test_hang_without_timeout_waits_full_duration(self, mock_sleep):
        with self.assertRaises(TimeoutError):
            maybe_inject(0)
        mock_sleep.assert_called_once_with(10.0)


class GeminiTimeoutTests(BaseTestCase):

    def tearDown(self):
        embedding_service._client = None
        llm_service._client = None

    @override_settings(GEMINI_API_KEY="k", GEMINI_EMBED_TIMEOUT_MS=2000)
    @patch("marketplace.services.embedding.genai.Client")
    def test_embedding_client_has_timeout(self, mock_client_cls):
        embedding_service._client = None
        embedding_service._get_client()
        self.assertEqual(mock_client_cls.call_args.kwargs["http_options"].timeout, 2000)

    @override_settings(GEMINI_API_KEY="k", GEMINI_LLM_TIMEOUT_MS=4000)
    @patch("marketplace.services.llm.genai.Client")
    def test_llm_client_has_timeout(self, mock_client_cls):
        llm_service._client = None
        llm_service._get_client()
        self.assertEqual(mock_client_cls.call_args.kwargs["http_options"].timeout, 4000)

    @override_settings(GEMINI_API_KEY="k", GEMINI_EMBED_TIMEOUT_MS=0)
    @patch("marketplace.services.embedding.genai.Client")
    def test_zero_means_no_timeout(self, mock_client_cls):
        embedding_service._client = None
        embedding_service._get_client()
        self.assertIsNone(mock_client_cls.call_args.kwargs["http_options"].timeout)
