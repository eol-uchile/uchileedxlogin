from django.contrib.auth.models import User
from django.db import models

from opaque_keys.edx.django.models import CourseKeyField

# Create your models here.


class EdxLoginUser(models.Model):
    class Meta:
        permissions = [
            ("instructor_staff", "instructor can enroll/unenroll users"),
        ]
    run = models.CharField(max_length=18, unique=True, db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, blank=False, null=False)


class EdxLoginUserCourseRegistration(models.Model):
    MODE_CHOICES = (("audit", "audit"), ("honor", "honor"))

    run = models.CharField(max_length=18, db_index=True)

    course = CourseKeyField(max_length=255)
    mode = models.TextField(choices=MODE_CHOICES)
    auto_enroll = models.BooleanField(default=True)
