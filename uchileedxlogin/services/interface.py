# Python Standard Libraries
import logging

# Internal project dependencies
from ..ph_query import get_user_data
from uchileedxlogin.models import EdxLoginUser
from uchileedxlogin.users import create_edxlogin_user_by_data
from uchileedxlogin.utils import validate_all_doc_id_types

logger = logging.getLogger(__name__)

# Interface exceptions.
class PhApiException(Exception):
    """
    Raised to indicate that the data related to the value provided to ph failed to get retrieved.
    """

class EmailException(Exception):
    """
    Raised to indicate that none of the mails associated with the doc_id are valid to create a
    edx user.
    """


def get_doc_id_by_user_id(user_id):
    """
    Return the document id associated with the user. If there is not a user with that id, returns None.
    """
    try:
        doc_id = EdxLoginUser.objects.values_list('run', flat=True).get(user__id=user_id)
        return doc_id
    except EdxLoginUser.DoesNotExist:
        return None

def get_user_id_doc_id_pairs(user_ids):
    """
    Returns a list containing the pairs user_id/doc_id associated with the users in user_ids.
    """
    users_doc_id_pairs = EdxLoginUser.objects.filter(user__id__in=user_ids).values_list('user__id', 'run')
    return users_doc_id_pairs

def get_user_by_doc_id(doc_id):
    """
    Get the user associated with doc_id, if it doesn't exists, return None.
    """
    try:
        edxloginuser = EdxLoginUser.objects.get(run=doc_id)
        return edxloginuser
    except EdxLoginUser.DoesNotExist:
        return None

def edxloginuser_factory(value, value_type):
    """
    Create an edxloginuser using value. Verifies if the value is valid.
    Tries to match the value with an already existing edx user, if it
    can't, creates a new edx user.
    The only value_type supported is doc_id.
    """
    if value_type == "doc_id":
        is_doc_id_valid = validate_all_doc_id_types(value)
        if not is_doc_id_valid:
            raise ValueError("doc_id: {value} doesn't match uchileedxlogin format.")
        try:
            user_data = get_user_data(value, 'indiv_id')
        except Exception as e:
            logger.warning(f"Factory failed for doc_id: {value}, with error: {e}")
            raise PhApiException()
        edxlogin_user = create_edxlogin_user_by_data(user_data)
        if not edxlogin_user:
            logger.warning(f"User can't be created because none of the mails are valid.")
            raise EmailException("User can't be created because none of the mails are valid.")
        return edxlogin_user
    else:
        logger.warning(f"Value type {value_type} is not supported by the edxloginuser factory.")
        return None

# Model permissions.
def check_permission_instructor_staff(user):
    """
    Check if the user has the permission uchile_instructor_staff.
    """
    if not user.is_anonymous:
        if user.has_perm('uchileedxlogin.uchile_instructor_staff') or user.is_staff:
            return True
        logger.error(f"Insufficient permissions, user: {user} isn't staff nor has special permission.")
    logger.error(f"Insufficient permissions, user: {user} is anonymous.")
    return False
