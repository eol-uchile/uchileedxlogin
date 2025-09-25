# Python Standard Libraries
import logging
import re
from itertools import cycle

# Installed packages (via pip)
import unidecode
from django.contrib.auth.models import User

# Edx dependencies
from common.djangoapps.student.models import CourseEnrollment, CourseEnrollmentAllowed
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from lms.djangoapps.courseware.access import has_access
from lms.djangoapps.courseware.courses import get_course_with_access

# Internal project dependencies
from uchileedxlogin.models import EdxLoginUser

logger = logging.getLogger(__name__)

def select_email(email_list):
    """
    Select an unused email from email_list following some criteria.
    """
    exists_user = User.objects.filter(email__in=email_list)
    if exists_user:
        emails = [user.email for user in exists_user]
        mails_without_edxuser = list(set(email_list) - set(emails))
        # Check if there is any email that is not being used in an eol account without a link.
        # In that case use any of them to create an user.
        if mails_without_edxuser:
            return mails_without_edxuser[0]
        else:
            return ''
    # If none of the emails have an edxuser, select the @uchile.cl one, otherwise choose the first one.
    elif email_list != []:
        selected_email = email_list[0]
        for email in email_list:
            if '@uchile.cl' in email:
                selected_email = email
        return selected_email
    else:
        return ''


def get_user_from_emails(email_list):
    """
    Check if there are any users associated with the given list of email addresses. 
    If multiple users are found, prioritize the @uchile.cl one, otherwise select whichever.
    """
    exists_user = User.objects.filter(email__in=email_list)
    if exists_user:
        users_without_link = []
        for user in exists_user:
            if not EdxLoginUser.objects.filter(user=user).exists() and user.is_active:
                if '@uchile.cl' in user.email:
                    return user
                else:
                    users_without_link.append(user)
        if users_without_link:
            return users_without_link[0]
    return None

        
def enroll_in_course(user, course, enroll, mode):
    """
    Enroll a user in course with mode "mode", if enroll is true, directly creates an enrollment,
    otherwise creates an enrollment allowed.
    """
    if enroll:
        CourseEnrollment.enroll(
            user,
            CourseKey.from_string(course),
            mode=mode)
    else:
        CourseEnrollmentAllowed.objects.create(
            course_id=CourseKey.from_string(course),
            email=user.email,
            user=user)


def validate_rut(rut):
    """
    Verify if the rut is valid.
    """
    rut = rut.upper()
    rut = rut.replace("-", "")
    rut = rut.replace(".", "")
    rut = rut.strip()
    aux = rut[:-1]
    dv = rut[-1:]
    revertido = list(map(int, reversed(str(aux))))
    factors = cycle(list(range(2, 8)))
    s = sum(d * f for d, f in zip(revertido, factors))
    res = (-s) % 11
    if str(res) == dv:
        return True
    elif dv == "K" and res == 10:
        return True
    else:
        return False


def validate_all_doc_id_types(doc_id):
    """
    Validate all document id types.
    """
    try:
        if doc_id[0] == 'P':
            if 5 > len(doc_id[1:]) or len(doc_id[1:]) > 20:
                logger.error("Invalid Passport: {}".format(doc_id))
                return False
        elif doc_id[0:2] == 'CG':
            if len(doc_id) != 10:
                logger.error("Invalid CG: {}".format(doc_id))
                return False
        else:
            if not validate_rut(doc_id):
                logger.error("Invalid document_id: {}".format(doc_id))
                return False
    except Exception:
        logger.error("Invalid: {}".format(doc_id))
        return False
    return True

def validate_course(course_id):
    """
    Verify if a course associated with course_id exists.
    """
    try:
        course_key = CourseKey.from_string(course_id)
        return CourseOverview.objects.filter(id=course_key).exists()
    except InvalidKeyError:
        return False


def generate_username(user_data):
    """
    Generate an username for the given user_data avoiding collitions with existing usernames.
    This generation will be done as follows, until one of the cases generates 
    an username without collision:
    0. return first_name[0] + N
    1. return first_name[0] + "_" + last_name[0]
    2. return first_name[0] + "_" + last_name[0] + "_" + last_name[1..N][0..N]
    3. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[0]
    4. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[0] + last_name[1..N][0..N]
    5. return first_name[0] + "_" + last_name[0] + N
    If a username can't be generated, raises an Exception.
    """
    USERNAME_MAX_LENGTH = 30
    if 'nombreCompleto' in user_data:
        aux_username = unidecode.unidecode(user_data['nombreCompleto'].lower())
        aux_username = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_username)
        aux_username = aux_username.split(" ")
        if len(aux_username) > 1:
            i = int(len(aux_username)/2)
            aux_first_name = aux_username[0:i]
            aux_last_name = aux_username[i:]
        # 0. Tries to create an username only using the first name and a number, in cases where
        # that name is the only name information in user_data.
        else:
            if User.objects.filter(username=aux_username[0]).exists():
                for i in range(1, 10000):
                    name_tmp = aux_username[0] + str(i)
                    if not User.objects.filter(username=name_tmp).exists():
                        return name_tmp
            else:
                return aux_username[0]
    else:
        aux_last_name = ((user_data['apellidoPaterno'] or '') +
                        " " + (user_data['apellidoMaterno'] or '')).strip()
        aux_last_name = unidecode.unidecode(aux_last_name)
        aux_last_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_last_name)
        aux_last_name = aux_last_name.split(" ")
        aux_first_name = unidecode.unidecode(user_data['nombres'])
        aux_first_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_first_name)
        aux_first_name = aux_first_name.split(" ")

    first_name = [x for x in aux_first_name if x != ''] or ['']
    last_name = [x for x in aux_last_name if x != ''] or ['']

    # 1. Tries to create an username using the first and last name.
    first_and_last_name = first_name[0] + "_" + last_name[0]
    if len(first_and_last_name) <= USERNAME_MAX_LENGTH and not User.objects.filter(
            username=first_and_last_name).exists():
        return first_and_last_name

    # 2. Tries to create an username concatenating letters from the others last names to firstName_lastName.
    fist_and_last_names = first_and_last_name
    for i in range(len(last_name[1:])):
        fist_and_last_names = fist_and_last_names + "_"
        for j in range(len(last_name[i + 1])):
            fist_and_last_names = fist_and_last_names + last_name[i + 1][j]
            if len(fist_and_last_names) > USERNAME_MAX_LENGTH:
                break
            if not User.objects.filter(username=fist_and_last_names).exists():
                return fist_and_last_names

    # 3. Tries to create an username concatenating the first name, with letter of other names and 
    # the first last name.
    first_names = first_name[0]
    for i in range(len(first_name[1:])):
        first_names = first_names + "_"
        for j in range(len(first_name[i + 1])):
            first_names = first_names + first_name[i + 1][j]
            first_names_and_last_name = first_names + "_" + last_name[0]
            if len(first_names_and_last_name) > USERNAME_MAX_LENGTH:
                break
            if not User.objects.filter(username=first_names_and_last_name).exists():
                return first_names_and_last_name

    # 4. Tries to create an username by concatenating the first and last name, with the other first
    # and last names.
    first_name_temp = first_name[0]
    for first_index in range(len(first_name[1:])):
        first_name_temp = first_name_temp + "_"
        for first_second_index in range(len(first_name[first_index + 1])):
            first_name_temp = first_name_temp + \
                first_name[first_index + 1][first_second_index]
            possible_name = first_name_temp + "_" + last_name[0]
            if len(possible_name) > USERNAME_MAX_LENGTH:
                break
            for second_index in range(len(last_name[1:])):
                possible_name = possible_name + "_"
                for second_second_index in range(
                        len(last_name[second_index + 1])):
                    possible_name = possible_name + \
                        last_name[second_index + 1][second_second_index]
                    if len(possible_name) > USERNAME_MAX_LENGTH:
                        break
                    if not User.objects.filter(
                            username=possible_name).exists():
                        return possible_name

    # 5. Tries to create an username using the first and last name and adding a number to the end.
    first_and_last_name = first_name[0] + "_" + last_name[0]
    # Truncate the name to assure that there is enough space to add numbers to the username.
    trunctated_first_and_last_name = first_and_last_name[0:(USERNAME_MAX_LENGTH - 5)]
    if trunctated_first_and_last_name[-1] == '_':
        trunctated_first_and_last_name = trunctated_first_and_last_name[:-1]
    for i in range(1, 10000):
        possible_name = trunctated_first_and_last_name + str(i)
        if not User.objects.filter(username=possible_name).exists():
            return possible_name
    # Username cant be generated
    raise Exception("Error generating username for user: {}".format(user_data))

def is_course_staff(user, course_id):
    """
    Verify if the user is staff course.
    """
    try:
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(user, "load", course_key)
        return bool(has_access(user, 'staff', course))
    except Exception:
        return False

def is_instructor(user, course_id):
    """
    Verify if the user is instructor.
    """
    try:
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(user, "load", course_key)
        return bool(has_access(user, 'instructor', course))
    except Exception:
        return False

def validate_user(user, course_id):
    """
    Verify if the user have permission.
    """
    access = False
    if not user.is_anonymous:
        if user.has_perm('uchileedxlogin.uchile_instructor_staff'):
            if user.is_staff:
                access = True
            if is_instructor(user, course_id):
                access = True
            if is_course_staff(user, course_id):
                access = True
    return access
