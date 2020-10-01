from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from .views import *


urlpatterns = [
    url('login/', EdxLoginLoginRedirect.as_view(), name='login'),
    url('callback/', EdxLoginCallback.as_view(), name='callback'),
    url('staff/$', EdxLoginStaff.as_view(), name='staff'),
    url('external/$', EdxLoginExternal.as_view(), name='external'),
    url('staff/export/$', staff_member_required(EdxLoginExport.as_view()), name='export'),
]
