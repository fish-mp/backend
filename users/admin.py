from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin

from users.models import CustomUser
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin

admin.site.unregister(Group)

@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

class CustomUserAdmin(UserAdmin, ModelAdmin):
    list_display = (
        "email",
        "first_name",
        "city",
        "age",
    )
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Персональная информация', {'fields': ('first_name', 'city', 'age')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'city', 'age'),
        }),
    )
    filter_horizontal = ('groups',)
    
    ordering = ('email',)
    search_fields = ('email', 'first_name', 'city')
    
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

admin.site.register(CustomUser, CustomUserAdmin)
