from unittest.mock import patch
from rest_framework import status
from rest_framework.authtoken.models import Token

from marketplace.models import (
    CustomUser,
    VerifiedUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
)
from marketplace.tests.base import BaseAPITestCase


class ApplicationAPITests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(category_name="Utilities", description="Utility apps")
        cls.os = OperatingSystem.objects.create(os_name="Windows")

        # Developer 1
        cls.dev1_user = CustomUser.objects.create_user(
            username="dev1",
            email="dev1@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="One",
            country="US",
            user_type="developer",
        )
        cls.dev1_profile = Developer.objects.create(
            user=cls.dev1_user,
            developer_alias="dev_alias_1",
            payment_method="upi",
            payment_details="dev1@upi",
        )
        cls.dev1_token = Token.objects.create(user=cls.dev1_user)

        # Developer 2
        cls.dev2_user = CustomUser.objects.create_user(
            username="dev2",
            email="dev2@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="Two",
            country="US",
            user_type="developer",
        )
        cls.dev2_profile = Developer.objects.create(
            user=cls.dev2_user,
            developer_alias="dev_alias_2",
            payment_method="upi",
            payment_details="dev2@upi",
        )
        cls.dev2_token = Token.objects.create(user=cls.dev2_user)

        # Customer
        cls.customer_user = CustomUser.objects.create_user(
            username="customer1",
            email="customer1@example.com",
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
        cls.customer_token = Token.objects.create(user=cls.customer_user)

        # Test app owned by dev1
        cls.app = Application.objects.create(
            developer=cls.dev1_profile,
            app_name="Test App",
            app_description="Test Description",
            price=9.99,
        )
        cls.app.categories.add(cls.category)
        cls.app.os.add(cls.os)

    @patch("django.test.client.store_rendered_templates")
    def test_swagger_ui_loads(self, mock_store):
        response = self.client.get("/api/schema/swagger-ui/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("django.test.client.store_rendered_templates")
    def test_browsable_api_renders(self, mock_store):
        response = self.client.get("/api/apps/", HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_application_crud(self):
        # Unauthenticated GET list
        res_list = self.client.get("/api/apps/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertIn("results", res_list.data)

        # POST as customer -> 403
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.customer_token.key)
        res_cust_post = self.client.post(
            "/api/apps/",
            {
                "app_name": "Cust App",
                "app_description": "Desc",
                "price": "5.00",
                "categories": [self.category.id],
                "os": [self.os.id],
            },
            format="json",
        )
        self.assertEqual(res_cust_post.status_code, status.HTTP_403_FORBIDDEN)

        # POST as developer -> 201
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.dev1_token.key)
        res_dev_post = self.client.post(
            "/api/apps/",
            {
                "app_name": "Dev App",
                "app_description": "Desc",
                "price": "5.00",
                "categories": [self.category.id],
                "os": [self.os.id],
            },
            format="json",
        )
        self.assertEqual(res_dev_post.status_code, status.HTTP_201_CREATED)
        created_app_id = res_dev_post.data["id"]

        # GET detail -> 200
        self.client.credentials()  # unauthenticated
        res_detail = self.client.get(f"/api/apps/{created_app_id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # PATCH as different developer -> 403
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.dev2_token.key)
        res_patch_dev2 = self.client.patch(
            f"/api/apps/{created_app_id}/",
            {"app_name": "Hacked App"},
            format="json",
        )
        self.assertEqual(res_patch_dev2.status_code, status.HTTP_403_FORBIDDEN)

        # PATCH as owning developer -> 200
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.dev1_token.key)
        res_patch_dev1 = self.client.patch(
            f"/api/apps/{created_app_id}/",
            {"app_name": "Updated Dev App"},
            format="json",
        )
        self.assertEqual(res_patch_dev1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch_dev1.data["app_name"], "Updated Dev App")

        # DELETE as owning developer -> 204
        res_delete_dev1 = self.client.delete(f"/api/apps/{created_app_id}/")
        self.assertIn(
            res_delete_dev1.status_code,
            [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK],
        )

    def test_read_only_endpoints(self):
        res_cat = self.client.get("/api/categories/")
        self.assertEqual(res_cat.status_code, status.HTTP_200_OK)

        res_os = self.client.get("/api/operating-systems/")
        self.assertEqual(res_os.status_code, status.HTTP_200_OK)
