from django.urls import path
from . import views

urlpatterns = [
    path('register/user/', views.verified_user_registration, name="verified_user_registration"),
    path('register/developer/', views.developer_registration, name="developer_registration"),
    path('apps/<int:app_id>/', views.view_app_details, name="app_details"),
    path('apps/<int:app_id>/review/', views.add_app_review, name="app_review"),
    path('apps/publish/', views.publish_app, name="app_publishing"),
    path('', views.home, name="homepage")
]