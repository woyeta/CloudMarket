from django.urls import path
from . import views

urlpatterns = [
    path('register/user/', views.verified_user_registration, name="verified_user_registration"),
    path('register/developer/', views.developer_registration, name="developer_registration"),
    path('', views.home, name="homepage")
]