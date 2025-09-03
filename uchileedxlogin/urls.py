from django.conf.urls import url
from .views import *


urlpatterns = [
    url('login/', EdxLoginLoginRedirect.as_view(), name='login'),
    url('callback/', EdxLoginCallback.as_view(), name='callback'),
    url('staff/$', EdxLoginStaff.as_view(), name='staff'),
    url('external/$', EdxLoginExternal.as_view(), name='external'),
]
