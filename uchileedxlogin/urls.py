from django.conf.urls import url
from .views import *


urlpatterns = [
    url('uchileedxlogin/login/', EdxLoginLoginRedirect.as_view(), name='login'),
    url('uchileedxlogin/callback/', EdxLoginCallback.as_view(), name='callback'),
    url('uchileedxlogin/staff/$', EdxLoginStaff.as_view(), name='staff'),
    url('uchileedxlogin/external/$', EdxLoginExternal.as_view(), name='external'),
    url('edxuserdata/data/', EdxLoginUserData.as_view(), name='data'),
]
