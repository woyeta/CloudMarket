from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from marketplace.api.views import (
    CategoryViewSet,
    OperatingSystemViewSet,
    ApplicationViewSet,
    ReviewViewSet,
    VerifiedUserRegistrationView,
    DeveloperRegistrationView,
    CurrentUserView,
    PaymentCreateView,
    PaymentListView,
    obtain_auth_token,
)
from marketplace.api.search import intent_search

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'operating-systems', OperatingSystemViewSet, basename='operatingsystem')
router.register(r'apps', ApplicationViewSet, basename='application')
router.register(r'apps/(?P<app_id>\d+)/reviews', ReviewViewSet, basename='app-review')

urlpatterns = [
    # Auth endpoints
    path('auth/register/user/', VerifiedUserRegistrationView.as_view(), name='register-user'),
    path('auth/register/developer/', DeveloperRegistrationView.as_view(), name='register-developer'),
    path('auth/login/', obtain_auth_token, name='token-login'),
    path('auth/me/', CurrentUserView.as_view(), name='current-user'),

    # Payment endpoints
    path('apps/<int:app_id>/purchase/', PaymentCreateView.as_view(), name='app-purchase'),
    path('payments/', PaymentListView.as_view(), name='payment-list'),

    # AI-powered intent search
    path('search/', intent_search, name='intent-search'),

    # drf-spectacular schema URLs
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # DefaultRouter URLs
    path('', include(router.urls)),
]
