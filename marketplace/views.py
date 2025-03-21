from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .models import VerifiedUser, Developer, Application
from .forms import VerifiedUserRegistrationForm, DeveloperRegistrationForm, ApplicationPublishForm, ApplicationReviewForm

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

@login_required
def publish_app(response):
    if not response.user.user_type=='developer':
        return redirect('/')
    
    if response.method=="POST":
        form = ApplicationPublishForm(response.POST)

        if form.is_valid():
            app = form.save(commit=False)
            app.developer = Developer.objects.get(user=response.user)
            app.save()
            form.save_m2m()

            return redirect(f'/apps/{app.id}/')
    
    form = ApplicationPublishForm()

    return render(response, 'marketplace/publish_app.html', {'form': form})

def view_app_details(response, app_id):
    app = get_object_or_404(Application, id=app_id)

    reviews = app.reviews_received.all().order_by('-creation_date')

    user_purchased = False

    context = {
        'app': app, 
        'reviews': reviews,
        'user_purchased': user_purchased,

    }

    return render(response, 'marketplace/app_details.html', context)

@login_required
def add_app_review(response, app_id):
    app = get_object_or_404(Application, id=app_id)

    if response.user.user_type=='developer':
        return redirect('/')
    
    if response.method=="POST":
        form = ApplicationReviewForm(response.POST, app=app, user=response.user)

        if form.is_valid():
            form.save()

        else:
            # Invalid Form
            # for field,error in form.errors.items():
            #     print(f"Error in {field}: {error}")
            pass
            
        return redirect(f'/apps/{app.id}/')
    
    form = ApplicationReviewForm(app=app, user=response.user)
    
    return render(response, 'marketplace/review_app.html', {'form': form, 'app_name': app.app_name})