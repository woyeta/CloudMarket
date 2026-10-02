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


class PaymentAPITests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(category_name="Finance", description="Finance apps")
        cls.os = OperatingSystem.objects.create(os_name="Linux")

        cls.dev_user = CustomUser.objects.create_user(
            username="pay_dev1",
            email="pay_dev1@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="One",
            country="US",
            user_type="developer",
        )
        cls.dev_profile = Developer.objects.create(
            user=cls.dev_user,
            developer_alias="pay_alias_1",
            payment_method="upi",
            payment_details="pay1@upi",
        )

        cls.customer_user = CustomUser.objects.create_user(
            username="pay_cust1",
            email="pay_cust1@example.com",
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

        cls.app = Application.objects.create(
            developer=cls.dev_profile,
            app_name="Pay App",
            app_description="Pay App Description",
            price=19.99,
        )
        cls.app.categories.add(cls.category)
        cls.app.os.add(cls.os)

    def test_payment(self):
        # POST purchase as authenticated user -> 201
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.customer_token.key)
        res_purchase = self.client.post(f"/api/apps/{self.app.id}/purchase/", format="json")
        self.assertEqual(res_purchase.status_code, status.HTTP_201_CREATED)

        # POST duplicate purchase -> 400
        res_dup_purchase = self.client.post(f"/api/apps/{self.app.id}/purchase/", format="json")
        self.assertEqual(res_dup_purchase.status_code, status.HTTP_400_BAD_REQUEST)

        # GET payments -> current user's purchases -> 200
        res_payments = self.client.get("/api/payments/")
        self.assertEqual(res_payments.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_payments.data["results"]), 1)
