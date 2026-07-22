from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import obtain_auth_token
from django.shortcuts import get_object_or_404

from marketplace.models import (
    Category,
    OperatingSystem,
    CustomUser,
    Application,
    Review,
    Payment,
)
from marketplace.api.serializers import (
    CategorySerializer,
    OperatingSystemSerializer,
    CustomUserSerializer,
    VerifiedUserRegistrationSerializer,
    DeveloperRegistrationSerializer,
    ApplicationListSerializer,
    ApplicationDetailSerializer,
    ReviewSerializer,
    PaymentSerializer,
    PaymentCreateSerializer,
)
from marketplace.api.permissions import (
    IsDeveloper,
    IsAppDeveloperOrReadOnly,
    IsReviewerOrReadOnly,
)


# 5.2 CategoryViewSet — ReadOnlyModelViewSet
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


# 5.3 OperatingSystemViewSet — ReadOnlyModelViewSet
class OperatingSystemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OperatingSystem.objects.all()
    serializer_class = OperatingSystemSerializer
    permission_classes = [permissions.AllowAny]


# 5.4 VerifiedUserRegistrationView — CreateAPIView
class VerifiedUserRegistrationView(generics.CreateAPIView):
    serializer_class = VerifiedUserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        user_serializer = CustomUserSerializer(user, context=self.get_serializer_context())
        return Response({
            'token': token.key,
            'user': user_serializer.data
        }, status=status.HTTP_201_CREATED)


# 5.5 DeveloperRegistrationView — CreateAPIView
class DeveloperRegistrationView(generics.CreateAPIView):
    serializer_class = DeveloperRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        user_serializer = CustomUserSerializer(user, context=self.get_serializer_context())
        return Response({
            'token': token.key,
            'user': user_serializer.data
        }, status=status.HTTP_201_CREATED)


# 5.6 CurrentUserView — RetrieveAPIView
class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = CustomUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# 5.7 ApplicationViewSet — ModelViewSet
class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all().order_by('-release_date')

    def get_serializer_class(self):
        if self.action == 'list':
            return ApplicationListSerializer
        return ApplicationDetailSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        elif self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, IsDeveloper]
        else:
            permission_classes = [permissions.IsAuthenticated, IsAppDeveloperOrReadOnly]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        developer_profile = getattr(self.request.user, 'developer_user', None)
        serializer.save(developer=developer_profile)


# 5.8 ReviewViewSet — ModelViewSet
class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer

    def get_queryset(self):
        app_id = self.kwargs.get('app_id')
        if app_id:
            return Review.objects.filter(app_reviewed_id=app_id)
        return Review.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        elif self.action == 'create':
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsReviewerOrReadOnly]
        return [permission() for permission in permission_classes]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        app_id = self.kwargs.get('app_id')
        if app_id:
            context['app_reviewed'] = get_object_or_404(Application, pk=app_id)
        return context

    def perform_create(self, serializer):
        app_id = self.kwargs.get('app_id')
        if app_id:
            app = get_object_or_404(Application, pk=app_id)
            serializer.save(reviewer=self.request.user, app_reviewed=app)
        else:
            serializer.save(reviewer=self.request.user)

    def perform_destroy(self, instance):
        app = instance.app_reviewed
        instance.delete()
        app.update_rating()


# 5.9 PaymentCreateView — CreateAPIView
class PaymentCreateView(generics.CreateAPIView):
    serializer_class = PaymentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        if 'app_id' in self.kwargs and 'app_purchased' not in data:
            data['app_purchased'] = self.kwargs['app_id']
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        app_id = self.kwargs.get('app_id')
        if app_id:
            app = get_object_or_404(Application, pk=app_id)
            serializer.save(payer=self.request.user, app_purchased=app)
        else:
            serializer.save(payer=self.request.user)


# 5.10 PaymentListView — ListAPIView
class PaymentListView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(payer=self.request.user)


# 5.11 Token Login View
obtain_auth_token = obtain_auth_token
