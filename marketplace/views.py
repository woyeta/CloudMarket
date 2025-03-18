from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import VerifiedUserRegistrationForm, DeveloperRegistrationForm

def home(response):
    return render(response, "marketplace/home.html", {})

def verified_user_registration(response):
    if response.method=="POST":
        form = VerifiedUserRegistrationForm(response.POST)

        if form.is_valid():
            user = form.save()
            login(response, user)

            return redirect("/")

    else:
        form = VerifiedUserRegistrationForm()

    return render(response, "marketplace/register_verified_user.html", {"form": form})

def developer_registration(response):
    if response.method=="POST":
        form = DeveloperRegistrationForm(response.POST)

        if form.is_valid():
            user = form.save()
            login(response, user)

            return redirect("/")

    else:
        form = DeveloperRegistrationForm()

    return render(response, "marketplace/register_developer.html", {"form": form})

def login_redirect(response):
    if response.user.is_authenticated:
        if response.user.user_type == 'customer':
            return redirect('/')
        elif response.user.user_type == 'developer':
            return redirect('/')
    
    return redirect('/')
