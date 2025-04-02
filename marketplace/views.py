from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .models import VerifiedUser, Developer, Application, Review, Payment
from .forms import VerifiedUserRegistrationForm, DeveloperRegistrationForm, ApplicationPublishForm, ApplicationReviewForm
import os
from django.conf import settings

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

    user_reviewed = False



    if response.user.is_authenticated:
        user_purchased = Payment.objects.filter(
            payer=response.user,
            app_purchased=app
        ).exists()

        user_reviewed = Review.objects.filter(
            reviewer=response.user, 
            app_reviewed=app
        ).exists()

    if response.method=="POST" and response.user.is_authenticated and not user_reviewed:
        form = ApplicationReviewForm(response.POST, app=app, user=response.user)

        if form.is_valid():
            form.save()
            
        return redirect(f'/apps/{app.id}/')
    else:
        if response.user.is_authenticated and not user_reviewed:
            form = ApplicationReviewForm(app=app, user=response.user)
        else:
            form = None

    context = {
        'app': app, 
        'reviews': reviews,
        'user_purchased': user_purchased,
        'review_form': form
    }

    return render(response, 'marketplace/app_details.html', context)

@login_required
def purchase_app(response, app_id):

    app = get_object_or_404(Application, id=app_id)

    if Payment.objects.filter(payer = response.user, app_purchased = app).exists():
        messages.info(response, "You have already purchased this application.")
        return redirect(f'/apps/{app_id}/')

    payment_method = 'upi'

    if response.user.user_type=='customer':
        try:
            verified_user = VerifiedUser.objects.get(user=response.user)
            payment_method = verified_user.payment_method
        
        except VerifiedUser.DoesNotExist:
            messages.error(response, "Your customer account is not verified for payments.")
            return redirect(f'/apps/{app_id}/')
    elif response.user.user_type=='developer':
        try:
            developer_user = Developer.objects.get(user=response.user)
            payment_method = developer_user.payment_method
        
        except Developer.DoesNotExist:
            messages.error(response, "Your developer account is not verified for payments.")
            return redirect(f'/apps/{app_id}/')
    
    payment = Payment.objects.create(
        payer=response.user,
        app_purchased=app,
        amount=app.price,
        method=payment_method
    )

    messages.success(response, f"You have successfully purchased {app.app_name}.")
    return redirect(f'/apps/{app_id}/')

@login_required
def download_app(request, app_id):
    
    app = get_object_or_404(Application, id=app_id)

    if not Payment.objects.filter(payer=request.user, app_purchased=app).exists():
        messages.error(request, "You need to purchase this app before downloading.")
        return redirect(f'/apps/{app_id}/')
    
    app.increment_downloads()

    placeholder_file_path = os.path.join(settings.MEDIA_ROOT, 'placeholder.jpg')

    if os.path.exists(placeholder_file_path):
        response = FileResponse(open(placeholder_file_path, 'rb'))
        response['Content-Disposition'] = 'attachment; filename="placeholder.jpg"'
        return response
    else:
        messages.error(request, "Download file is missing.")
        return redirect(f'/apps/{app_id}/')