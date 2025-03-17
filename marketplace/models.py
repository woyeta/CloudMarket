from django.db import models
from django.db.models import Avg
from django.contrib.auth.models import AbstractUser, Group, Permission
from django_countries.fields import CountryField
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.
class CustomUser(AbstractUser):
    USER_TYPES = (
        ('customer', 'Customer'),
        ('developer', 'Developer')
    )

    user_type = models.CharField(max_length=9, choices=USER_TYPES)

    first_name = models.CharField(max_length=50, blank=False, null = False)
    last_name = models.CharField(max_length=50, blank=False, null = False)
    email = models.EmailField(unique=True, blank=False, null= False)
    creation_date = models.DateField(auto_now_add=True)
    country = CountryField()

    groups = models.ManyToManyField(Group, related_name="customer_users", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="customer_users_permissions", blank=True)

    def __str__(self):
        return f"{self.id} {self.first_name}"


class VerifiedUser(CustomUser):
    PAYMENT_CHOICES = (
        ('upi', 'UPI'),
        ('card', 'Card')
    )
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="verified_user")
    payment_method = models.CharField(max_length=4, choices=PAYMENT_CHOICES, blank=False, null=False, default='upi')

class Developer(CustomUser):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="developer_user")
    developer_alias = models.CharField(max_length=15, unique=True, blank = False, null = False)
    payment_details = models.CharField(max_length=51, unique=False, blank = False, null = False)

class Category(models.Model):
    category_name = models.CharField(max_length=25, unique = True, blank = False, null = False)
    description = models.CharField(max_length=150, unique = True, blank = False, null = False)

class OperatingSystem(models.Model):
    os_name = models.CharField(max_length=25, unique = True, blank = False, null = False)

class Application(models.Model):
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='developed_apps')
    app_name = models.CharField(max_length=25, unique = True, blank = False, null = False)
    app_description = models.CharField(max_length=150, unique = True, blank = False, null = True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], blank = False, null = False, default=0)
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    os = models.ManyToManyField(OperatingSystem, related_name='os_apps')
    downloads = models.IntegerField(default=0.0, validators=[MinValueValidator(0)])
    release_date = models.DateField(auto_now_add=True)


    def update_rating(self):
        avg_rating = self.reviews.aggregate(avg_rating = Avg('rating'))['avg_rating']
        self.rating = avg_rating if avg_rating is not None else 0.0
        self.save()
    
    def increment_downloads(self):
        self.downloads = self.downloads+1
        self.save()

    def __str__(self):
        return self.app_name
    

class Review(models.Model):
    reviewer = models.ForeignKey(VerifiedUser, on_delete=models.CASCADE, related_name="reviews_made")
    app_reviewed = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="reviews_received")
    rating_given = models.IntegerField(default= 1, blank = False, null= False, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=100, blank = True, null = True)
    creation_date = models.DateField(auto_now_add=True)


class Payment(models.Model):
    PAYMENT_CHOICES = (
        ('upi', 'UPI'),
        ('card', 'Card')
    )
    payer = models.ForeignKey(VerifiedUser, on_delete=models.CASCADE, related_name="payments_made")
    app_purchased = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="payments_received")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    payment_date = models.DateField(auto_now_add=True)
    method = models.CharField(max_length=4, choices = PAYMENT_CHOICES)

    class Meta:
        unique_together = ('payer', 'app_purchased')

