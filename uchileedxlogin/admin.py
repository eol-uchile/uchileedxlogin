from django.contrib import admin
from .models import EdxLoginUser, EdxLoginUserCourseRegistration

# Register your models here.


class EdxLoginUserAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    list_display = ('run', 'user')
    search_fields = ['run', 'user__username']
    ordering = ['-run']


class EdxLoginUserCourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ('run', 'course')
    search_fields = ['run', 'course']
    ordering = ['-course']


admin.site.register(EdxLoginUser, EdxLoginUserAdmin)
admin.site.register(
    EdxLoginUserCourseRegistration,
    EdxLoginUserCourseRegistrationAdmin)
