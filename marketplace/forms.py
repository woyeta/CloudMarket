from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import CustomUser, VerifiedUser, Developer, Application, Category, OperatingSystem, Review

class VerifiedUserRegistrationForm(UserCreationForm):
    PAYMENT_CHOICES = (
        ('upi', 'UPI'),
        ('card', 'Card')
    )
    payment_method = forms.ChoiceField(choices=PAYMENT_CHOICES, required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'country']

    def save(self, commit=True):
        user = super().save(commit=False)

        user.user_type = 'customer'

        if commit:
            user.save()

            VerifiedUser.objects.create(
                user=user,
                payment_method = self.cleaned_data['payment_method']
            )
        
        return user


class DeveloperRegistrationForm(UserCreationForm):
    developer_alias = forms.CharField(max_length=15, required=True, help_text="Your developer alias")
    payment_details = forms.CharField(max_length=51, required=True, help_text="Your UPI id")

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'country']

    def save(self, commit=True):
        user = super().save(commit=False)

        user.user_type = 'developer'

        if commit:
            user.save()

            Developer.objects.create(
                user=user,
                developer_alias = self.cleaned_data['developer_alias'],
                payment_details = self.cleaned_data['payment_details']
            )
        
        return user

class ApplicationPublishForm(forms.ModelForm):

    categories = forms.ModelMultipleChoiceField(
        queryset= Category.objects.all(),
        widget = forms.CheckboxSelectMultiple(),
        required = False
    )

    os = forms.ModelMultipleChoiceField(
        queryset= OperatingSystem.objects.all(),
        widget = forms.CheckboxSelectMultiple(),
        required = False
    )

    class Meta:
        model = Application
        fields = ['app_name', 'app_description', 'price', 'categories', 'os']

        widgets = {
            'app_description': forms.Textarea(attrs={'rows': 4}),
        }

class ApplicationReviewForm(forms.ModelForm):
    REVIEW_RATING_CHOICES = (
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5')
    )

    rating_given = forms.ChoiceField(
        choices=REVIEW_RATING_CHOICES,
        widget=forms.RadioSelect(),
        required=True,
        label="Rating",
    )

    comment = forms.CharField(
        widget=forms.Textarea(attrs={'rows':3}),
        required=False,
        label="Comment",
    )

    class Meta:
        model = Review
        fields = ['rating_given', 'comment']

    def __init__(self, *args, **kwargs):
        self.app = kwargs.pop('app', None)
        self.user = kwargs.pop('user', None)

        super(ApplicationReviewForm, self).__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        
        if not self.user:
            raise forms.ValidationError("User is required to submit a review.")
        
        else:
            existing_review = Review.objects.filter(
                reviewer=self.user, 
                app_reviewed=self.app
            ).exists()
            
            if existing_review:
                raise forms.ValidationError("You have already reviewed this application.")
        
        return cleaned_data
    
    def save(self, commit=True):
        review = super().save(commit=False)
        
        if self:
            review.reviewer = self.user
            review.app_reviewed = self.app
        
        if commit:
            review.save()
            self.app.update_rating()
        
        return review