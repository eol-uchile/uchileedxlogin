
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
from django.conf import settings
from lms.djangoapps.courseware.courses import get_course_by_id
from opaque_keys.edx.keys import UsageKey, CourseKey

from celery import task
from django.core.mail import send_mail
from django.utils.html import strip_tags

from django.template.loader import render_to_string

import logging
logger = logging.getLogger(__name__)

EMAIL_DEFAULT_RETRY_DELAY = 30
EMAIL_MAX_RETRIES = 5

@task(
    queue='edx.lms.core.low',
    default_retry_delay=EMAIL_DEFAULT_RETRY_DELAY,
    max_retries=EMAIL_MAX_RETRIES)
def enroll_email(user_pass, user_email, course_id, redirect_url, is_sso, exists, login_url, user_name):
    """
        Send mail to specific user
    """
    platform_name = configuration_helpers.get_value(
            'PLATFORM_NAME', settings.PLATFORM_NAME)
    course = get_course_by_id(CourseKey.from_string(course_id))
    subject = 'Inscripción en el curso: {}'.format(course.display_name_with_default)
    context = {
        "course_name": course.display_name_with_default,
        "platform_name": platform_name,
        "user_password": user_pass,
        'redirect_url': redirect_url,
        'user_email': user_email,
        'login_url': login_url,
        'user_name': user_name
    }
    if is_sso:
        html_message = render_to_string('emails/sso_email.txt', context)
    elif exists:
        html_message = render_to_string('emails/exists_user_email.txt', context)
    else:
        html_message = render_to_string('emails/normal_email.txt', context)
    plain_message = strip_tags(html_message)
    from_email = configuration_helpers.get_value(
        'email_from_address',
        settings.BULK_EMAIL_DEFAULT_FROM_EMAIL
    )
    mail = send_mail(
        subject,
        plain_message,
        from_email,
        [user_email],
        fail_silently=False,
        html_message=html_message)
    return mail