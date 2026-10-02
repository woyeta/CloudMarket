from rest_framework import status
from rest_framework.authtoken.models import Token

from marketplace.models import CustomUser, VerifiedUser
from marketplace.tests.base import BaseAPITestCase


class AuthAPITests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
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

    def test_user_registration_flow(self):
        # Register user (customer)
        cust_data = {
            "username": "newcust",
            "first_name": "New",
            "last_name": "Cust",
            "email": "newcust@example.com",
            "password": "Password123!",
            "country": "US",
            "payment_method": "upi",
        }
        res_cust = self.client.post("/api/auth/register/user/", cust_data, format="json")
        self.assertEqual(res_cust.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", res_cust.data)
        self.assertIn("user", res_cust.data)

        # Register developer
        dev_data = {
            "username": "newdev",
            "first_name": "New",
            "last_name": "Dev",
            "email": "newdev@example.com",
            "password": "Password123!",
            "country": "US",
            "developer_alias": "newdev_alias",
            "payment_details": "newdev@upi",
            "payment_method": "upi",
        }
        res_dev = self.client.post("/api/auth/register/developer/", dev_data, format="json")
        self.assertEqual(res_dev.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", res_dev.data)
        self.assertIn("user", res_dev.data)

    def test_token_login(self):
        login_data = {
            "username": "customer1",
            "password": "Password123!",
        }
        response = self.client.post("/api/auth/login/", login_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_current_user(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.customer_token.key)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "customer1")
