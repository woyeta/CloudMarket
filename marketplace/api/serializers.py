from rest_framework import serializers
from django.db import transaction
from django_countries.serializer_fields import CountryField
from marketplace.models import (
    CustomUser,
    VerifiedUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
    Review,
    Payment,
)

# 3.3.1 CategorySerializer — ModelSerializer for Category (all fields, read-only)
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['id', 'category_name', 'description']


# 3.3.2 OperatingSystemSerializer — ModelSerializer for OperatingSystem (all fields, read-only)
class OperatingSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperatingSystem
        fields = '__all__'
        read_only_fields = ['id', 'os_name']


# 3.3.3 CustomUserSerializer — ModelSerializer for CustomUser (read-only representation: id, username, first_name, last_name, email, country, user_type, creation_date)
class CustomUserSerializer(serializers.ModelSerializer):
    country = CountryField(read_only=True)

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'country', 'user_type', 'creation_date']
        read_only_fields = ['id', 'username', 'first_name', 'last_name', 'email', 'country', 'user_type', 'creation_date']


# 3.3.4 VerifiedUserRegistrationSerializer
class VerifiedUserRegistrationSerializer(serializers.ModelSerializer):
    payment_method = serializers.ChoiceField(choices=VerifiedUser.PAYMENT_CHOICES, required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'password', 'country', 'payment_method']

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate_username(self, value):
        if CustomUser.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        payment_method = validated_data.pop('payment_method')
        password = validated_data.pop('password')
        with transaction.atomic():
            user = CustomUser.objects.create_user(
                user_type='customer',
                password=password,
                **validated_data
            )
            VerifiedUser.objects.create(
                user=user,
                payment_method=payment_method
            )
        return user


# 3.3.5 DeveloperRegistrationSerializer
class DeveloperRegistrationSerializer(serializers.ModelSerializer):
    developer_alias = serializers.CharField(max_length=15, required=True)
    payment_details = serializers.CharField(max_length=51, required=True)
    payment_method = serializers.ChoiceField(choices=Developer.PAYMENT_CHOICES, required=False, default='upi')
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'password', 'country', 'developer_alias', 'payment_details', 'payment_method']

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate_username(self, value):
        if CustomUser.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_developer_alias(self, value):
        if Developer.objects.filter(developer_alias=value).exists():
            raise serializers.ValidationError("A developer with this alias already exists.")
        return value

    def create(self, validated_data):
        developer_alias = validated_data.pop('developer_alias')
        payment_details = validated_data.pop('payment_details')
        payment_method = validated_data.pop('payment_method', 'upi')
        password = validated_data.pop('password')
        with transaction.atomic():
            user = CustomUser.objects.create_user(
                user_type='developer',
                password=password,
                **validated_data
            )
            Developer.objects.create(
                user=user,
                developer_alias=developer_alias,
                payment_details=payment_details,
                payment_method=payment_method
            )
        return user


# 3.3.6 ApplicationListSerializer
class ApplicationListSerializer(serializers.ModelSerializer):
    developer_alias = serializers.SerializerMethodField()
    categories = serializers.StringRelatedField(many=True, read_only=True)
    os = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Application
        fields = ['id', 'app_name', 'price', 'rating', 'downloads', 'release_date', 'developer_alias', 'categories', 'os']

    def get_developer_alias(self, obj):
        if hasattr(obj, 'developer') and obj.developer:
            return obj.developer.developer_alias
        return None


# 3.3.7 ApplicationDetailSerializer
class ApplicationDetailSerializer(serializers.ModelSerializer):
    developer_alias = serializers.SerializerMethodField()
    categories = serializers.PrimaryKeyRelatedField(many=True, queryset=Category.objects.all())
    os = serializers.PrimaryKeyRelatedField(many=True, queryset=OperatingSystem.objects.all())

    class Meta:
        model = Application
        fields = ['id', 'developer', 'developer_alias', 'app_name', 'app_description', 'price', 'rating', 'os', 'downloads', 'release_date', 'categories']
        read_only_fields = ['developer', 'rating', 'downloads', 'release_date']

    def get_developer_alias(self, obj):
        if hasattr(obj, 'developer') and obj.developer:
            return obj.developer.developer_alias
        return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['categories'] = CategorySerializer(instance.categories.all(), many=True).data
        representation['os'] = OperatingSystemSerializer(instance.os.all(), many=True).data
        return representation


# 3.3.8 ReviewSerializer
class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'reviewer', 'app_reviewed', 'rating_given', 'comment', 'creation_date']
        read_only_fields = ['reviewer', 'app_reviewed', 'creation_date']

    def validate_rating_given(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        reviewer = None
        if request and hasattr(request, 'user'):
            reviewer = request.user
        elif 'reviewer' in attrs:
            reviewer = attrs['reviewer']

        app_reviewed = attrs.get('app_reviewed') or self.context.get('app_reviewed')

        if reviewer and app_reviewed and not self.instance:
            if Review.objects.filter(reviewer=reviewer, app_reviewed=app_reviewed).exists():
                raise serializers.ValidationError("You have already reviewed this application.")
        return attrs


# 3.3.9 PaymentSerializer (read-only for list)
class PaymentSerializer(serializers.ModelSerializer):
    app_purchased = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'payer', 'app_purchased', 'amount', 'payment_date', 'method']
        read_only_fields = ['id', 'payer', 'app_purchased', 'amount', 'payment_date', 'method']


# 3.3.10 PaymentCreateSerializer (write for create)
class PaymentCreateSerializer(serializers.ModelSerializer):
    app_purchased = serializers.PrimaryKeyRelatedField(queryset=Application.objects.all())

    class Meta:
        model = Payment
        fields = ['app_purchased']

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required to make a payment.")

        user = request.user
        has_verified_profile = hasattr(user, 'verified_user') or hasattr(user, 'developer_user')
        if not has_verified_profile:
            raise serializers.ValidationError("User must have a verified profile for payments.")

        app_purchased = attrs.get('app_purchased')
        if Payment.objects.filter(payer=user, app_purchased=app_purchased).exists():
            raise serializers.ValidationError("You have already purchased this application.")

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        app = validated_data['app_purchased']
        amount = app.price

        if hasattr(user, 'verified_user'):
            method = user.verified_user.payment_method
        elif hasattr(user, 'developer_user'):
            method = user.developer_user.payment_method
        else:
            method = 'upi'

        with transaction.atomic():
            payment = Payment.objects.create(
                payer=user,
                app_purchased=app,
                amount=amount,
                method=method
            )
            app.increment_downloads()

        return payment


# Intent Search Serializers
class IntentSearchRequestSerializer(serializers.Serializer):
    """Validates the incoming search request."""
    query = serializers.CharField(
        max_length=300,
        required=True,
        help_text="Natural language search query, e.g. 'I want to learn guitar as a beginner'",
    )


class IntentSearchAppSerializer(serializers.ModelSerializer):
    """
    Serializes matched apps for the search response.
    Includes developer alias, categories, and OS as readable strings.
    """
    developer_alias = serializers.SerializerMethodField()
    categories = serializers.StringRelatedField(many=True, read_only=True)
    os = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'app_name', 'app_description', 'price', 'rating',
            'downloads', 'release_date', 'developer_alias', 'categories', 'os',
        ]

    def get_developer_alias(self, obj):
        if hasattr(obj, 'developer') and obj.developer:
            return obj.developer.developer_alias
        return None


class IntentSearchResponseSerializer(serializers.Serializer):
    """Defines the shape of the search response for documentation."""
    apps = IntentSearchAppSerializer(many=True)
    explanation = serializers.CharField(allow_null=True)
    error = serializers.CharField(allow_null=True)
