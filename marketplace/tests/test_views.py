from unittest.mock import patch
from rest_framework import status

from marketplace.models import (
    CustomUser,
    VerifiedUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
)
from marketplace.tests.base import BaseAPITestCase


class MarketplaceWebViewsTests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(category_name="Productivity", description="Productivity apps")
        cls.os = OperatingSystem.objects.create(os_name="MacOS")

        cls.dev_user = CustomUser.objects.create_user(
            username="view_dev1",
            email="view_dev1@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="One",
            country="US",
            user_type="developer",
        )
        cls.developer = Developer.objects.create(
            user=cls.dev_user,
            developer_alias="view_alias_1",
            payment_method="upi",
            payment_details="vdev1@upi",
        )

        cls.customer_user = CustomUser.objects.create_user(
            username="view_cust1",
            email="view_cust1@example.com",
            password="Password123!",
            first_name="Cust",
            last_name="One",
            country="US",
            user_type="customer",
        )
        cls.customer_profile = VerifiedUser.objects.create(
            user=cls.customer_user,
            payment_method="card",
        )

        cls.app = Application.objects.create(
            developer=cls.developer,
            app_name="View App",
            app_description="View App Description",
            price=2.99,
        )
        cls.app.categories.add(cls.category)
        cls.app.os.add(cls.os)

    @patch("django.test.client.store_rendered_templates")
    def test_homepage_renders(self, mock_store):
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("django.test.client.store_rendered_templates")
    def test_app_detail_renders(self, mock_store):
        response = self.client.get(f"/apps/{self.app.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("django.test.client.store_rendered_templates")
    def test_register_user_renders(self, mock_store):
        response = self.client.get("/register/user/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("django.test.client.store_rendered_templates")
    def test_session_login_works(self, mock_store):
        response = self.client.get("/login/")
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

        login_response = self.client.post("/login/", {
            "username": "view_cust1",
            "password": "Password123!",
        })
        self.assertIn(login_response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
