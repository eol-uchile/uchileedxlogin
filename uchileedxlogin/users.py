# Python Standard Libraries
import logging

# Edx dependencies
from common.djangoapps.student.helpers import do_create_account
from django.contrib.auth.base_user import BaseUserManager
from openedx.core.djangoapps.user_authn.views.registration_form import AccountCreationForm

# Internal project dependencies
from uchileedxlogin.models import EdxLoginUser
from uchileedxlogin.utils import get_user_from_emails, generate_username, select_email

logger = logging.getLogger(__name__)

def create_user_by_data(user_data, email, password=None):
    """
    Create an eol user using user_data, email and an optional password.
    """
    username = generate_username(user_data)
    if 'nombreCompleto' not in user_data:
        user_data['nombreCompleto'] = '{} {} {}'.format(user_data['nombres'], user_data['apellidoPaterno'], user_data['apellidoMaterno'])
    if not password:
        password = BaseUserManager().make_random_password(12)
    form = AccountCreationForm(
        data={
            "username": username,
            "email": email,
            "password": password,
            "name": user_data['nombreCompleto'],
        },
        tos_required=False,
        ignore_email_blacklist=True
    )
    user, _, reg = do_create_account(form)
    reg.activate()
    reg.save()
    return user


def create_edxlogin_user_by_data(user_data):
    """
    Create an edxloginuser using user_data. 
    Returns None if a user can't be created due to not finding neither a suitable user nor email.
    """
    user = get_user_from_emails(user_data['emails'])
    if not user:
        email = select_email(user_data['emails'])
        if not email:
            return None
        user = create_user_by_data(user_data, email, None)
    edxlogin_user = create_edxloginuser(user, True, user_data["doc_id"])
    return edxlogin_user


def create_edxloginuser(user, have_sso, doc_id):
    """
    Create an edxloginuser using a user, have_sso and a doc_id.
    Returns None if edxloginuser failed to be created.
    """
    try:
        edxlogin_user = EdxLoginUser.objects.create(
            user=user,
            have_sso=have_sso,
            run=doc_id
        )
        return edxlogin_user
    except Exception as e:
        logger.error(f"create_edxloginuser failed for user: {user}, have_sso: {have_sso} and doc_id: {doc_id}, with error: {e}")
        raise Exception(f"Failed to create EdxLoginUser object for user: {user}, have_sso: {have_sso} and doc_id: {doc_id}")
