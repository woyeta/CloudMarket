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


class ReviewAPITests(BaseAPITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(category_name="Games", description="Games apps")
        cls.os = OperatingSystem.objects.create(os_name="Windows")

        cls.dev1_user = CustomUser.objects.create_user(
            username="rev_dev1",
            email="rev_dev1@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="One",
            country="US",
            user_type="developer",
        )
        cls.dev1_profile = Developer.objects.create(
            user=cls.dev1_user,
            developer_alias="rev_alias_1",
            payment_method="upi",
            payment_details="rev1@upi",
        )

        cls.dev2_user = CustomUser.objects.create_user(
            username="rev_dev2",
            email="rev_dev2@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="Two",
            country="US",
            user_type="developer",
        )
        cls.dev2_profile = Developer.objects.create(
            user=cls.dev2_user,
            developer_alias="rev_alias_2",
            payment_method="upi",
            payment_details="rev2@upi",
        )
        cls.dev2_token = Token.objects.create(user=cls.dev2_user)

        cls.customer_user = CustomUser.objects.create_user(
            username="rev_cust1",
            email="rev_cust1@example.com",
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
            developer=cls.dev1_profile,
            app_name="Review App",
            app_description="Review App Description",
            price=4.99,
        )
        cls.app.categories.add(cls.category)
        cls.app.os.add(cls.os)

    def test_review_crud(self):
        # GET reviews list -> 200
        res_list = self.client.get(f"/api/apps/{self.app.id}/reviews/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        # POST review as authenticated user -> 201
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.customer_token.key)
        res_create = self.client.post(
            f"/api/apps/{self.app.id}/reviews/",
            {
                "rating_given": 5,
                "comment": "Great app!",
            },
            format="json",
        )
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        review_id = res_create.data["id"]

        # POST duplicate review -> 400
        res_dup = self.client.post(
            f"/api/apps/{self.app.id}/reviews/",
            {
                "rating_given": 4,
                "comment": "Duplicate review",
            },
            format="json",
        )
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # PATCH review as author -> 200
        res_patch = self.client.patch(
            f"/api/apps/{self.app.id}/reviews/{review_id}/",
            {"comment": "Updated comment"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["comment"], "Updated comment")

        # DELETE review as different user -> 403
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.dev2_token.key)
        res_delete_other = self.client.delete(f"/api/apps/{self.app.id}/reviews/{review_id}/")
        self.assertEqual(res_delete_other.status_code, status.HTTP_403_FORBIDDEN)
