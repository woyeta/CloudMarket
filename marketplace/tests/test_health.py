from unittest.mock import MagicMock, patch

import fakeredis
import redis
from django.test import override_settings

from marketplace.tests.base import BaseTestCase


class HealthzTests(BaseTestCase):

    def test_healthy_db_without_redis(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "checks": {"db": "ok", "redis": "disabled"}})

    @patch("marketplace.health.connection")
    def test_db_down_returns_503(self, mock_connection):
        mock_connection.cursor.side_effect = Exception("connection refused")
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["checks"]["db"], "down")

    @override_settings(REDIS_URL="redis://fake:6379/0")
    @patch("marketplace.services.cache._client")
    def test_redis_ok(self, mock_client):
        mock_client.return_value = fakeredis.FakeRedis()
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["checks"]["redis"], "ok")

    @patch("marketplace.services.cache._client")
    def test_redis_down_is_degraded_not_503(self, mock_client):
        broken = MagicMock()
        broken.ping.side_effect = redis.ConnectionError("down")
        mock_client.return_value = broken
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["checks"]["redis"], "degraded")

    def test_only_get_allowed(self):
        res = self.client.post("/healthz")
        self.assertEqual(res.status_code, 405)
