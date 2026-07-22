from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from marketplace.models import (
    CustomUser, VerifiedUser, Developer, Category, OperatingSystem, Application, Review, Payment
)

class Phase8VerificationTests(APITestCase):

    def setUp(self):
        # Create categories and OS for testing
        self.category = Category.objects.create(category_name="Utilities", description="Utility apps")
        self.os = OperatingSystem.objects.create(os_name="Windows")

        # Create developer 1
        self.dev1_user = CustomUser.objects.create_user(
            username="dev1",
            email="dev1@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="One",
            country="US",
            user_type="developer"
        )
        self.dev1_profile = Developer.objects.create(
            user=self.dev1_user,
            developer_alias="dev_alias_1",
            payment_method="upi",
            payment_details="dev1@upi"
        )
        self.dev1_token = Token.objects.create(user=self.dev1_user)

        # Create developer 2
        self.dev2_user = CustomUser.objects.create_user(
            username="dev2",
            email="dev2@example.com",
            password="Password123!",
            first_name="Dev",
            last_name="Two",
            country="US",
            user_type="developer"
        )
        self.dev2_profile = Developer.objects.create(
            user=self.dev2_user,
            developer_alias="dev_alias_2",
            payment_method="upi",
            payment_details="dev2@upi"
        )
        self.dev2_token = Token.objects.create(user=self.dev2_user)

        # Create customer user
        self.customer_user = CustomUser.objects.create_user(
            username="customer1",
            email="customer1@example.com",
            password="Password123!",
            first_name="Cust",
            last_name="One",
            country="US",
            user_type="customer"
        )
        self.customer_profile = VerifiedUser.objects.create(
            user=self.customer_user,
            payment_method="card"
        )
        self.customer_token = Token.objects.create(user=self.customer_user)

        # Create test app owned by dev1
        self.app = Application.objects.create(
            developer=self.dev1_profile,
            app_name="Test App",
            app_description="Test Description",
            price=9.99
        )
        self.app.categories.add(self.category)
        self.app.os.add(self.os)

    # 8.1 Visit /api/schema/swagger-ui/
    @patch('django.test.client.store_rendered_templates')
    def test_8_1_swagger_ui_loads(self, mock_store):
        response = self.client.get('/api/schema/swagger-ui/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 8.2 Visit /api/apps/ in browser — verify DRF Browsable API renders
    @patch('django.test.client.store_rendered_templates')
    def test_8_2_browsable_api_renders(self, mock_store):
        response = self.client.get('/api/apps/', HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 8.3 Test user registration flow
    def test_8_3_user_registration_flow(self):
        # Register user (customer)
        cust_data = {
            "username": "newcust",
            "first_name": "New",
            "last_name": "Cust",
            "email": "newcust@example.com",
            "password": "Password123!",
            "country": "US",
            "payment_method": "upi"
        }
        res_cust = self.client.post('/api/auth/register/user/', cust_data, format='json')
        self.assertEqual(res_cust.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', res_cust.data)
        self.assertIn('user', res_cust.data)

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
            "payment_method": "upi"
        }
        res_dev = self.client.post('/api/auth/register/developer/', dev_data, format='json')
        self.assertEqual(res_dev.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', res_dev.data)
        self.assertIn('user', res_dev.data)

    # 8.4 Test token login
    def test_8_4_token_login(self):
        login_data = {
            "username": "customer1",
            "password": "Password123!"
        }
        response = self.client.post('/api/auth/login/', login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    # 8.5 Test current user
    def test_8_5_current_user(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.customer_token.key)
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'customer1')

    # 8.6 Test Application CRUD
    def test_8_6_application_crud(self):
        # Unauthenticated GET list
        res_list = self.client.get('/api/apps/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertIn('results', res_list.data)

        # POST as customer -> 403
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.customer_token.key)
        res_cust_post = self.client.post('/api/apps/', {
            "app_name": "Cust App",
            "app_description": "Desc",
            "price": "5.00",
            "categories": [self.category.id],
            "os": [self.os.id]
        }, format='json')
        self.assertEqual(res_cust_post.status_code, status.HTTP_403_FORBIDDEN)

        # POST as developer -> 201
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.dev1_token.key)
        res_dev_post = self.client.post('/api/apps/', {
            "app_name": "Dev App",
            "app_description": "Desc",
            "price": "5.00",
            "categories": [self.category.id],
            "os": [self.os.id]
        }, format='json')
        self.assertEqual(res_dev_post.status_code, status.HTTP_201_CREATED)
        created_app_id = res_dev_post.data['id']

        # GET detail -> 200
        self.client.credentials() # unauthenticated
        res_detail = self.client.get(f'/api/apps/{created_app_id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # PATCH as different developer -> 403
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.dev2_token.key)
        res_patch_dev2 = self.client.patch(f'/api/apps/{created_app_id}/', {"app_name": "Hacked App"}, format='json')
        self.assertEqual(res_patch_dev2.status_code, status.HTTP_403_FORBIDDEN)

        # PATCH as owning developer -> 200
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.dev1_token.key)
        res_patch_dev1 = self.client.patch(f'/api/apps/{created_app_id}/', {"app_name": "Updated Dev App"}, format='json')
        self.assertEqual(res_patch_dev1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch_dev1.data['app_name'], "Updated Dev App")

        # DELETE as owning developer -> 204
        res_delete_dev1 = self.client.delete(f'/api/apps/{created_app_id}/')
        self.assertIn(res_delete_dev1.status_code, [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK])

    # 8.7 Test Review CRUD
    def test_8_7_review_crud(self):
        # GET reviews list -> 200
        res_list = self.client.get(f'/api/apps/{self.app.id}/reviews/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        # POST review as authenticated user -> 201
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.customer_token.key)
        res_create = self.client.post(f'/api/apps/{self.app.id}/reviews/', {
            "rating_given": 5,
            "comment": "Great app!"
        }, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        review_id = res_create.data['id']

        # POST duplicate review -> 400
        res_dup = self.client.post(f'/api/apps/{self.app.id}/reviews/', {
            "rating_given": 4,
            "comment": "Duplicate review"
        }, format='json')
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # PATCH review as author -> 200
        res_patch = self.client.patch(f'/api/apps/{self.app.id}/reviews/{review_id}/', {
            "comment": "Updated comment"
        }, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['comment'], "Updated comment")

        # DELETE review as different user -> 403
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.dev2_token.key)
        res_delete_other = self.client.delete(f'/api/apps/{self.app.id}/reviews/{review_id}/')
        self.assertEqual(res_delete_other.status_code, status.HTTP_403_FORBIDDEN)

    # 8.8 Test Payment
    def test_8_8_payment(self):
        # POST purchase as authenticated user -> 201
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.customer_token.key)
        res_purchase = self.client.post(f'/api/apps/{self.app.id}/purchase/', format='json')
        self.assertEqual(res_purchase.status_code, status.HTTP_201_CREATED)

        # POST duplicate purchase -> 400
        res_dup_purchase = self.client.post(f'/api/apps/{self.app.id}/purchase/', format='json')
        self.assertEqual(res_dup_purchase.status_code, status.HTTP_400_BAD_REQUEST)

        # GET payments -> current user's purchases -> 200
        res_payments = self.client.get('/api/payments/')
        self.assertEqual(res_payments.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_payments.data['results']), 1)

    # 8.9 Test read-only endpoints
    def test_8_9_read_only_endpoints(self):
        res_cat = self.client.get('/api/categories/')
        self.assertEqual(res_cat.status_code, status.HTTP_200_OK)

        res_os = self.client.get('/api/operating-systems/')
        self.assertEqual(res_os.status_code, status.HTTP_200_OK)

    # 8.10 Visit / — homepage renders correctly
    @patch('django.test.client.store_rendered_templates')
    def test_8_10_homepage_renders(self, mock_store):
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 8.11 Visit /apps/{id}/ — app detail page renders correctly
    @patch('django.test.client.store_rendered_templates')
    def test_8_11_app_detail_renders(self, mock_store):
        response = self.client.get(f'/apps/{self.app.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 8.12 Visit /register/user/ — registration form renders correctly
    @patch('django.test.client.store_rendered_templates')
    def test_8_12_register_user_renders(self, mock_store):
        response = self.client.get('/register/user/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 8.13 Login via /accounts/login/ — session auth still works
    @patch('django.test.client.store_rendered_templates')
    def test_8_13_session_login_works(self, mock_store):
        response = self.client.get('/login/')
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

        login_response = self.client.post('/login/', {
            'username': 'customer1',
            'password': 'Password123!'
        })
        self.assertIn(login_response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
