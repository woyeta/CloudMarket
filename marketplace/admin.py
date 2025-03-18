from django.contrib import admin
from .models import (
    CustomUser, 
    VerifiedUser, 
    Developer, 
    Category, 
    OperatingSystem, 
    Application, 
    Review, 
    Payment
)

admin.site.register(CustomUser)
admin.site.register(VerifiedUser)
admin.site.register(Developer)
admin.site.register(Category)
admin.site.register(OperatingSystem)
admin.site.register(Application)
admin.site.register(Review)
admin.site.register(Payment)