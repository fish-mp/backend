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
        ('Персональная информация', {'fields': ('first_name', 'city', 'age', 'is_email_verified')}),
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


from users.models import LegalConsent


@admin.register(LegalConsent)
class LegalConsentAdmin(ModelAdmin):
    list_display = ('user', 'purpose', 'document_version', 'accepted_at')
    list_filter = ('purpose', 'document_version')
    readonly_fields = ('user', 'purpose', 'object_id', 'document_version', 'document_sha256', 'document_snapshot', 'accepted_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
