from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APITestCase


class SignalPatchMixin:
    """
    Mixin that patches _compute_and_store_embedding with a mock before setUpClass
    to avoid spawning background DB query threads and tracebacks during non-signal tests.
    """
    @classmethod
    def setUpClass(cls):
        cls._signal_patcher = patch("marketplace.signals._compute_and_store_embedding")
        cls._signal_patcher.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._signal_patcher.stop()


class BaseTestCase(SignalPatchMixin, TestCase):
    pass


class BaseAPITestCase(SignalPatchMixin, APITestCase):
    pass
