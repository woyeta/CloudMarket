from unittest.mock import patch

from marketplace.tests.base import BaseTestCase


class HealthzTests(BaseTestCase):

    def test_healthy_db(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "checks": {"db": "ok"}})

    @patch("marketplace.health.connection")
    def test_db_down_returns_503(self, mock_connection):
        mock_connection.cursor.side_effect = Exception("connection refused")
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["checks"]["db"], "down")

    def test_only_get_allowed(self):
        res = self.client.post("/healthz")
        self.assertEqual(res.status_code, 405)
