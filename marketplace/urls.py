from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('register/user/', views.verified_user_registration, name="verified_user_registration"),
    path('register/developer/', views.developer_registration, name="developer_registration"),
    path('apps/<int:app_id>/', views.view_app_details, name="app_details"),
    path('apps/publish/', views.publish_app, name="app_publishing"),
    path('', views.home, name="homepage"),
    path('apps/<int:app_id>/purchase/', views.purchase_app, name='purchase_app'),
    path('apps/<int:app_id>/download/', views.download_app, name='download_app'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)