from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import CustomUser, VerifiedUser, Developer, Application, Category, OperatingSystem

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

