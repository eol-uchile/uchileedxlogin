#!/usr/bin/env python
# -- coding: utf-8 --

# Python Standard Libraries
import base64
import logging
import re
from urllib.parse import urlencode

# Installed packages (via pip)
import requests
import unidecode
import unicodecsv as csv
from common.djangoapps.student.models import CourseEnrollment, CourseEnrollmentAllowed
from common.djangoapps.util.json_request import JsonResponse
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.base import View

# Edx dependencies
from lms.djangoapps.courseware.courses import get_course_by_id
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.user_authn.utils import is_safe_login_or_logout_redirect

# Internal project dependencies
from .email_tasks import enroll_email
from .ph_query import check_doc_id_have_sso, get_user_data
from .models import EdxLoginUserCourseRegistration
from .services.interface import check_permission_instructor_staff, edxloginuser_factory, get_doc_id_by_user_id, get_user_by_doc_id
from .services.utils import validate_rut
from .users import create_edxloginuser, create_edxlogin_user_by_data, create_user_by_data
from .utils import enroll_in_course, validate_all_doc_id_types, validate_course, validate_user

logger = logging.getLogger(__name__)
regex = r'^(([^ñáéíóú<>()\[\]\.,;:\s@\"]+(\.[^ñáéíóú<>()\[\]\.,;:\s@\"]+)*)|(\".+\"))@(([^ñáéíóú<>()[\]\.,;:\s@\"]+\.)+[^ñáéíóú<>()[\]\.,;:\s@\"]{2,})$'
regex_names = r'^[A-Za-z\s\_]+$'


def require_post_action():
    """
    Checks for required parameters or renders a 400 error.
    (decorator with arguments)

    `args` is a *list of required POST parameter names.
    `kwargs` is a **dict of required POST parameter names
        to string explanations of the parameter
    """
    def decorator(func):  # pylint: disable=missing-docstring
        def wrapped(*args, **kwargs):  # pylint: disable=missing-docstring
            request = args[1]
            action = request.POST.get("action", "")
            error_response_data = {
                'error': 'Missing required query parameter(s)',
                'parameters': ["action"],
                'info': {"action": action},
            }
            if action in ["enroll", "unenroll", "staff_enroll"]:
                return func(*args, **kwargs)
            else:
                return JsonResponse(error_response_data, status=400)

        return wrapped
    return decorator

class EdxLoginLoginRedirect(View):
    def get(self, request):
        redirect_url = request.GET.get('next', "/")
        if request.user.is_authenticated:
            return HttpResponseRedirect(redirect_url)

        return HttpResponseRedirect(
            '{}?{}'.format(
                settings.EDXLOGIN_REQUEST_URL,
                urlencode(
                    self.service_parameters(request))))

    def service_parameters(self, request):
        """
        Store the service parameter for uchileedxlogin.
        """
        parameters = {
            'service': EdxLoginLoginRedirect.get_callback_url(request),
            'renew': 'true'
        }
        return parameters

    @staticmethod
    def get_callback_url(request):
        """
        Get the callback url.
        """
        import base64
        redirect_url = base64.b64encode(request.GET.get('next', "/").encode("utf-8")).decode("utf-8")
        url = request.build_absolute_uri(
            reverse('uchileedxlogin-login:callback'))
        return '{}?next={}'.format(url, redirect_url)


class EdxLoginCallback(View):
    def get(self, request):
        ticket = request.GET.get('ticket')
        redirect_url = base64.b64decode(
            request.GET.get(
                'next', "Lw==")).decode('utf-8')
        if not is_safe_login_or_logout_redirect(redirect_url, request.get_host(), None, False):
            redirect_url = "/"
        error_url = reverse('uchileedxlogin-login:login')

        if ticket is None:
            logger.exception("Error ticket")
            return HttpResponseRedirect(
                '{}?next={}'.format(
                    error_url, redirect_url))

        username = self.verify_state(request, ticket)
        if username is None:
            logger.exception("Error username ")
            return HttpResponseRedirect(
                '{}?next={}'.format(
                    error_url, redirect_url))
        try:
            is_logged = self.login_user(request, username)
            if not is_logged:
                return HttpResponseRedirect('{}?next={}'.format(error_url, redirect_url))
        except Exception:
            logger.exception("Error logging {}, with ticket: {}".format(username, ticket))
            return HttpResponseRedirect(
                '{}?next={}'.format(
                    error_url, redirect_url))
        return HttpResponseRedirect(redirect_url)

    def verify_state(self, request, ticket):
        """
        Verify if the ticket is correct.
        """
        url = request.build_absolute_uri(
            reverse('uchileedxlogin-login:callback'))
        parameters = {
            'service': '{}?next={}'.format(
                url,
                request.GET.get('next')),
            'ticket': ticket,
            'renew': 'true'}
        result = requests.get(
            settings.EDXLOGIN_RESULT_VALIDATE,
            params=urlencode(parameters),
            headers={
                'content-type': 'application/x-www-form-urlencoded',
                'User-Agent': 'curl/7.58.0'})
        if result.status_code == 200:
            r = result.content.decode('utf-8').split('\n')
            if r[0] == 'yes':
                return r[1]

        return None

    def login_user(self, request, username):
        """
        Log in the uchile user with the account linked to it, creating a eol account if there
        wasn't any associated to the user.
        """
        user_data = get_user_data(username, 'usuario')
        doc_id = user_data['doc_id']
        edxlogin_user = get_user_by_doc_id(doc_id)
        if not edxlogin_user:
            try:
               edxlogin_user = create_edxlogin_user_by_data(user_data)
               if not edxlogin_user:
                   logger.error(f"User can't be created because none of the mails are valid.")
                   return False
            except Exception as e:
                logger.error(f'Error when trying to create edxloginuser with doc_id: {doc_id} and error: {e}')
                return False
        if not edxlogin_user.have_sso:
            edxlogin_user.have_sso = True
            edxlogin_user.save()
        self.enroll_pending_courses(edxlogin_user)
        if request.user.is_anonymous or request.user.id != edxlogin_user.user.id:
            logout(request)
            login(
                request,
                edxlogin_user.user,
                backend="django.contrib.auth.backends.AllowAllUsersModelBackend",
            )
        return True

    def enroll_pending_courses(self, edxlogin_user):
        """
        Enroll the user in the pending courses, removing the enrollments when
        they are applied.
        """
        registrations = EdxLoginUserCourseRegistration.objects.filter(
            run=edxlogin_user.run)
        for item in registrations:
            if item.auto_enroll:
                CourseEnrollment.enroll(
                    edxlogin_user.user, item.course, mode=item.mode)
            else:
                CourseEnrollmentAllowed.objects.create(
                    course_id=item.course,
                    email=edxlogin_user.user.email,
                    user=edxlogin_user.user)
        registrations.delete()


class EdxLoginStaff(View):
    """
    Enroll/force enroll/unenroll user.
    """
    def get(self, request):
        if check_permission_instructor_staff(request.user):
            context = {'doc_ids': '', 'auto_enroll': True, 'modo': 'audit', 'curso':''}
            return render(request, 'edxlogin/staff.html', context)
        else:
            raise Http404()

    @require_post_action()
    def post(self, request):
        if check_permission_instructor_staff(request.user):
            action = request.POST.get("action", "")
            doc_id_list = request.POST.get("doc_ids", "").split('\n')
            # Document id formatting
            doc_id_list = [doc_id.upper() for doc_id in doc_id_list]
            doc_id_list = [doc_id.replace("-", "") for doc_id in doc_id_list]
            doc_id_list = [doc_id.replace(".", "") for doc_id in doc_id_list]
            doc_id_list = [doc_id.strip() for doc_id in doc_id_list]
            doc_id_list = [doc_id for doc_id in doc_id_list if doc_id]

            #  Verifies if auto-enroll is checked
            enroll = False
            if request.POST.getlist("enroll"):
                enroll = True

            # If Force is checked, set force variable to true.
            force = False
            if request.POST.getlist("force"):
                force = True

            context = {
                'doc_ids': request.POST.get('doc_ids'),
                'action': action,
                'curso': request.POST.get(
                    "course",
                    ""),
                'auto_enroll': enroll,
                'modo': request.POST.get(
                    "modes",
                    None)}
            context = self.validate_data(request.user, doc_id_list, context)
            # Returns is there is at least one error
            if len(context) > 5 and action not in ["enroll", "unenroll"]:
                return render(request, 'edxlogin/staff.html', context)
            if len(context) > 5 and action in ["enroll", "unenroll"]:
                return JsonResponse(context)

            list_course = context['curso'].split('\n')
            list_course = [course_id.strip() for course_id in list_course]
            list_course = [course_id for course_id in list_course if course_id]
            if action in ["enroll", "staff_enroll"]:
                context = self.enroll_or_create_users(
                    list_course, context['modo'], doc_id_list, force, enroll)
                if action in ["enroll"]:
                    return JsonResponse(context)
                return render(request, 'edxlogin/staff.html', context)

            elif action == "unenroll":
                context = self.unenroll_user(list_course, doc_id_list)
                return JsonResponse(context)
            else:
                #Cambiar este log, deberia ser algo como invalid action y nose si se deberia raisear un 404
                logger.error("User doesn't have permission or is not staff, user: {}".format(request.user))
                raise Http404()
        else:
            raise Http404()
        
    def validate_data(self, user, doc_id_list, context):
        """
        Verify if the data if valid.
        """
        invalid_doc_ids = ""
        original_doc_ids = []
        duplicate_doc_ids = []
        original_courses = []
        duplicate_courses = []
        # doc_id validation
        for doc_id in doc_id_list:
            try:
                if doc_id[0] == 'P':
                    if 5 > len(doc_id[1:]) or len(doc_id[1:]) > 20:
                        invalid_doc_ids += doc_id + " - "
                elif doc_id[0:2] == 'CG':
                    if len(doc_id) != 10:
                        invalid_doc_ids += doc_id + " - "
                else:
                    if not validate_rut(doc_id):
                        invalid_doc_ids += doc_id + " - "
                if doc_id in original_doc_ids:
                    duplicate_doc_ids.append(doc_id)
                else:
                    original_doc_ids.append(doc_id)
            except Exception:
                invalid_doc_ids += doc_id + " - "

        invalid_doc_ids = invalid_doc_ids[:-3]

        # Other fields validation
        # If there is a wrong doc_id
        if invalid_doc_ids != "":
            context['invalid_doc_ids'] = invalid_doc_ids
        if len(duplicate_doc_ids) > 0:
            context['duplicate_doc_ids'] = duplicate_doc_ids
        # Validate course
        if context['curso'] == "":
            context['curso2'] = ''
        # Validate if the course exists
        else:
            list_course = context['curso'].split('\n')
            list_course = [course_id.strip() for course_id in list_course]
            list_course = [course_id for course_id in list_course if course_id]
            for course_id in list_course:
                if course_id in original_courses:
                    duplicate_courses.append(course_id)
                else:
                    original_courses.append(course_id)
                if not validate_course(course_id):
                    if 'error_curso' not in context:
                        context['error_curso'] = [course_id]
                    else:
                        context['error_curso'].append(course_id)
                    logger.error("EdxLoginStaff - Course doesn't exists, user: {}, course_id: {}".format(user.id, course_id))
            if 'error_curso' not in context:
                for course_id in list_course:
                    if not validate_user(user, course_id):
                        if 'error_permission' not in context:
                            context['error_permission'] = [course_id]
                        else:
                            context['error_permission'].append(course_id)
                        logger.error("EdxLoginStaff - User doesn't have permission, user: {}, course_id: {}".format(user.id, course_id))
        if len(duplicate_courses) > 0:
            context['duplicate_courses'] = duplicate_courses
        # If there was no doc_id
        if not doc_id_list:
            context['no_doc_id'] = ''
        # If the mode is incorrect
        if not context['modo'] in [
                x[0] for x in EdxLoginUserCourseRegistration.MODE_CHOICES]:
            context['error_mode'] = ''
        # If action is incorrect
        if not context['action'] in [
                "enroll",
                "unenroll",
                "staff_enroll"]:
            context['error_action'] = ''
        return context
        

    def enroll_or_create_users(self, course_ids, mode, doc_id_list, force, enroll):
        """
        Enroll/force enroll users.
        """
        doc_id_saved_force = ""
        doc_id_saved_force_no_auto = ""
        doc_id_saved_pending = ""
        doc_id_saved_enroll = ""
        doc_id_saved_enroll_no_auto = ""
        # guarda el form
        with transaction.atomic():
            for doc_id in doc_id_list:
                while len(doc_id) < 10 and 'P' != doc_id[0] and 'CG' != doc_id[0:2]:
                    doc_id = "0" + doc_id
                edxlogin_user = get_user_by_doc_id(doc_id)
                if edxlogin_user:
                    for course_id in course_ids:
                        enroll_in_course(edxlogin_user.user, course_id, enroll, mode)
                    if enroll:
                        doc_id_saved_enroll += edxlogin_user.user.username + " - " + doc_id + " / "
                    else:
                        doc_id_saved_enroll_no_auto += edxlogin_user.user.username + " - " + doc_id + " / "
                else:
                    if force:
                        try:
                            edxlogin_user = edxloginuser_factory(doc_id, 'doc_id')
                        except:
                            pass
                    if edxlogin_user:
                        for course_id in course_ids:
                            enroll_in_course(edxlogin_user.user, course_id, enroll, mode)
                        if enroll:
                            doc_id_saved_force += edxlogin_user.user.username + " - " + doc_id + " / "
                        else:
                            doc_id_saved_force_no_auto += edxlogin_user.user.username + " - " + doc_id + " / "
                    else:
                        for course_id in course_ids:
                            registro = EdxLoginUserCourseRegistration()
                            registro.run = doc_id
                            registro.course = course_id
                            registro.mode = mode
                            registro.auto_enroll = enroll
                            registro.save()
                        doc_id_saved_pending += doc_id + " - "
        doc_id_saved = {
            'doc_id_saved_force': doc_id_saved_force[:-3],
            'doc_id_saved_pending': doc_id_saved_pending[:-3],
            'doc_id_saved_enroll': doc_id_saved_enroll[:-3],
            'doc_id_saved_enroll_no_auto': doc_id_saved_enroll_no_auto[:-3],
            'doc_id_saved_force_no_auto': doc_id_saved_force_no_auto[:-3]
        }
        return {
            'doc_ids': '',
            'curso': '',
            'auto_enroll': True,
            'modo': 'audit',
            'saved': 'saved',
            'doc_id_saved': doc_id_saved}

    def unenroll_user(self, course_ids, doc_id_list):
        """
        Unenroll user.
        """
        course_keys = [CourseKey.from_string(course_id) for course_id in course_ids]
        doc_id_list_format = []
        doc_id_unenroll_pending = []
        doc_id_unenroll_allowed = []
        doc_id_unenroll_enroll = []
        for doc_id in doc_id_list:
            while len(doc_id) < 10 and 'P' != doc_id[0] and 'CG' != doc_id[0:2]:
                doc_id = "0" + doc_id
            doc_id_list_format.append(doc_id)

        with transaction.atomic():
            #unenroll EdxLoginUserCourseRegistration
            registrations = EdxLoginUserCourseRegistration.objects.filter(
                run__in=doc_id_list_format, course__in=course_keys)
            if registrations:
                doc_id_unenroll_pending = [x.run for x in registrations]
                registrations.delete()
            #unenroll CourseEnrollmentAllowed
            enrollmentAllowed = CourseEnrollmentAllowed.objects.filter(
                course_id__in=course_keys, user__edxloginuser__run__in=doc_id_list_format)
            if enrollmentAllowed:
                doc_id_unenroll_allowed = [x.user.edxloginuser.run for x in enrollmentAllowed]
                enrollmentAllowed.delete()
            #unenroll CourseEnrollment
            enrollment = CourseEnrollment.objects.filter(user__edxloginuser__run__in=doc_id_list_format, course_id__in=course_keys)
            if enrollment:
                doc_id_unenroll_enroll = [x.user.edxloginuser.run for x in enrollment]
                enrollment.update(is_active=0)
        aux_doc_id_unenroll = doc_id_unenroll_pending
        aux_doc_id_unenroll.extend(doc_id_unenroll_allowed)
        aux_doc_id_unenroll.extend(doc_id_unenroll_enroll)
        doc_id_unenroll = []
        for i in aux_doc_id_unenroll:
            if i not in doc_id_unenroll:
                doc_id_unenroll.append(i)
        doc_id_unenroll_no_exists = [x for x in doc_id_list_format if x not in doc_id_unenroll]
        return {
            'doc_ids': '',
            'auto_enroll': True,
            'modo': 'honor',
            'saved': 'unenroll',
            'doc_id_unenroll_no_exists': doc_id_unenroll_no_exists,
            'doc_id_unenroll': doc_id_unenroll}


class EdxLoginExternal(View):
    """
        Enroll external user
    """
    def get(self, request):
        if check_permission_instructor_staff(request.user):
            context = {'datos': '', 'auto_enroll': True, 'modo': 'honor', 'send_email': True, 'curso': ''}
            return render(request, 'edxlogin/external.html', context)
        else:
            raise Http404()

    def post(self, request):
        if check_permission_instructor_staff(request.user):
            lista_data = request.POST.get("datos", "").lower().split('\n')
            # limpieza de los datos ingresados
            lista_data = [doc_id.strip() for doc_id in lista_data]
            lista_data = [doc_id for doc_id in lista_data if doc_id]
            lista_data = [d.split(",") for d in lista_data]
            # verifica si el checkbox de auto enroll fue seleccionado
            enroll = False
            if request.POST.getlist("enroll"):
                enroll = True
            # verifica si el checkbox de send_email fue seleccionado
            send_email = False
            if request.POST.getlist("send_email"):
                send_email = True
            context = {
                'datos': request.POST.get('datos'),
                'curso': request.POST.get("course", ""),
                'auto_enroll': enroll,
                'send_email': send_email,
                'modo': request.POST.get("modes", None)}
            # validacion de datos
            context = self.validate_data_external(request.user, lista_data, context)
            # retorna si hubo al menos un error
            if len(context) > 5:
                return render(request, 'edxlogin/external.html', context)
            list_course = context['curso'].split('\n')
            list_course = [course_id.strip() for course_id in list_course]
            list_course = [course_id for course_id in list_course if course_id]

            lista_saved, lista_not_saved = self.enroll_create_user(
                list_course, context['modo'], lista_data, enroll)

            login_url = request.build_absolute_uri('/login')
            helpdesk_url = request.build_absolute_uri('/contact_form')
            email_saved = []
            courses = [get_course_by_id(CourseKey.from_string(course_id)) for course_id in list_course]
            courses_name = ''
            for course in courses:
                courses_name = courses_name + course.display_name_with_default + ', '
            courses_name = courses_name[:-2]
            for email in lista_saved:
                if send_email:
                    if 'email2' in email:
                        enroll_email.delay(email['password'], email['email'], courses_name, email['sso'], email['exists'], login_url, email['nombreCompleto'], helpdesk_url, email['email2'])
                    else:
                        enroll_email.delay(email['password'], email['email'], courses_name, email['sso'], email['exists'], login_url, email['nombreCompleto'], helpdesk_url, '')
                aux = email
                aux.pop('password', None)
                email_saved.append(aux)

            context = {
                'datos': '',
                'auto_enroll': True,
                'send_email': True,
                'curso': '',
                'modo': 'honor',
                'action_send': send_email
            }
            if len(email_saved) > 0:
                context['lista_saved'] = email_saved
            if len(lista_not_saved) > 0:
                context['lista_not_saved'] = lista_not_saved
            return render(request, 'edxlogin/external.html', context)
        else:
            raise Http404()

    def validate_data_external(self, user, lista_data, context):
        """
            Validate Data
        """
        wrong_data = []
        duplicate_data = [[],[]]
        original_data = [[],[]]
        duplicate_courses = []
        original_courses = []
        # si no se ingreso datos
        if not lista_data:
            logger.error("EdxLoginExternal - Empty Data, user: {}".format(user.id))
            context['no_data'] = ''
        if len(lista_data) > 50:
            logger.error("EdxLoginExternal - data limit is 50, length data: {} user: {}".format(len(lista_data),user.id))
            context['limit_data'] = ''
        else:
            for data in lista_data:
                data = [d.strip() for d in data]
                if len(data) == 1 or len(data)>3:
                    data.append("")
                    data.append("")
                    wrong_data.append(data)
                    logger.error("EdxLoginExternal - Wrong Data, only one or four++ parameters, user: {}, invalid_data: {}".format(user.id, wrong_data))
                else:
                    if len(data) == 2:
                        data.append("")
                    else:
                        data[2] = data[2].upper()
                    if data[0] != "" and data[1] != "":
                        aux_name = unidecode.unidecode(data[0])
                        aux_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_name)
                        if not re.match(regex_names, aux_name):
                            logger.error("EdxLoginExternal - Invalid Name, not allowed specials characters, user: {}, invalid_data: {}".format(user.id, wrong_data))
                            wrong_data.append(data)
                        elif not re.match(regex, data[1]):
                            logger.error("EdxLoginExternal - Invalid Email {}, user: {}, invalid_data: {}".format(data[1], user.id, wrong_data))
                            wrong_data.append(data)
                        elif data[2] != "" and not validate_all_doc_id_types(data[2]):
                            logger.error("EdxLoginExternal - Invalid doc_id {}, user: {}, invalid_data: {}".format(data[2], user.id, wrong_data))
                            wrong_data.append(data)
                        elif data[1] in original_data[0] or (data[2] != '' and data[2] in original_data[1]):
                            if data[1] in original_data[0]:
                                duplicate_data[0].append(data[1])
                            if data[2] != '' and data[2] in original_data[1]:
                                duplicate_data[1].append(data[2])
                        else:
                            original_data[0].append(data[1])
                            if data[2] != '':
                                original_data[1].append(data[2])
                    else:
                        wrong_data.append(data)
        if len(wrong_data) > 0:
            logger.error("EdxLoginExternal - Wrong Data, user: {}, wrong_data: {}".format(user.id, wrong_data))
            context['wrong_data'] = wrong_data
        if len(duplicate_data[0]) > 0:
            logger.error("EdxLoginExternal - Duplicate Email, user: {}, duplicate_data: {}".format(user.id, duplicate_data[0]))
            context['duplicate_email'] = duplicate_data[0]
        if len(duplicate_data[1]) > 0:
            logger.error("EdxLoginExternal - Duplicate doc_id, user: {}, duplicate_data: {}".format(user.id, duplicate_data[1]))
            context['duplicate_doc_id'] = duplicate_data[1]
        # valida curso
        if context['curso'] == "":
            logger.error("EdxLoginExternal - Empty course, user: {}".format(user.id))
            context['curso2'] = ''

        # valida si existe el curso
        else:
            list_course = context['curso'].split('\n')
            list_course = [course_id.strip() for course_id in list_course]
            list_course = [course_id for course_id in list_course if course_id]
            for course_id in list_course:
                if course_id in original_courses:
                    duplicate_courses.append(course_id)
                else:
                    original_courses.append(course_id)
                if not validate_course(course_id):
                    if 'error_curso' not in context:
                        context['error_curso'] = [course_id]
                    else:
                        context['error_curso'].append(course_id)
                    logger.error("EdxLoginExternal - Course dont exists, user: {}, course_id: {}".format(user.id, course_id))
            if 'error_curso' not in context:
                for course_id in list_course:
                    if not validate_user(user, course_id):
                        if 'error_permission' not in context:
                            context['error_permission'] = [course_id]
                        else:
                            context['error_permission'].append(course_id)
                        logger.error("EdxLoginExternal - User dont have permission, user: {}, course_id: {}".format(user.id, course_id))
        if len(duplicate_courses) > 0:
            context['duplicate_courses'] = duplicate_courses
        # si el modo es incorrecto
        if not context['modo'] in [
                x[0] for x in EdxLoginUserCourseRegistration.MODE_CHOICES]:
            context['error_mode'] = ''
            logger.error("EdxLoginExternal - Wrong Mode, user: {}, mode: {}".format(user.id, context['modo']))
        return context

    def enroll_create_user(self, course_ids, mode, lista_data, enroll):
        """
        Create and enroll the user with/without UChile account
        if email or doc_id exists not saved them
        """
        lista_saved = []
        lista_not_saved = []
        # guarda el form
        with transaction.atomic():
            for dato in lista_data:
                dato = [d.strip() for d in dato]
                if len(dato) == 3:
                    dato[2] = dato[2].upper()
                    dato[2] = dato[2].replace("-", "")
                    dato[2] = dato[2].replace(".", "")
                    dato[2] = dato[2].strip()
                if len(dato) == 2:
                    dato.append("")
                while len(dato[2]) > 0 and len(dato[2]) < 10 and 'P' != dato[2][0] and 'CG' != dato[2][0:2]:
                    dato[2] = "0" + dato[2]
                aux_pass = BaseUserManager().make_random_password(12)
                aux_pass = aux_pass.lower()
                user_exists = False
                if dato[2] != "":
                    aux_email = ''
                    edxlogin_user = get_user_by_doc_id(dato[2])
                    if edxlogin_user is not None:
                        if not edxlogin_user.have_sso:
                            if edxlogin_user.user.email != dato[1]:
                                aux_email = edxlogin_user.user.email
                    else:
                        edxlogin_user, created = self.get_or_create_user_with_doc_id(dato, aux_pass)
                        if not created and edxlogin_user is not None:
                            user_exists = True
                    if edxlogin_user is None:
                        lista_not_saved.append([dato[1], dato[2]])
                    else:
                        for course_id in course_ids:
                            enroll_in_course(edxlogin_user.user, course_id, enroll, mode)
                        aux_append = {
                            'email': dato[1],
                            'nombreCompleto': edxlogin_user.user.profile.name.strip(),
                            'doc_id': dato[2],
                            'password': aux_pass,
                            'sso': edxlogin_user.have_sso,
                            'exists': user_exists
                        }
                        if aux_email != '':
                            aux_append['email2'] = aux_email
                        lista_saved.append(aux_append)
                else:
                    doc_id = ''
                    have_sso = False
                    try:
                        user = User.objects.get(email=dato[1])
                        user_exists = True
                        doc_id = get_doc_id_by_user_id(user.id)
                        if doc_id is not None:
                            edxlogin_user = get_user_by_doc_id(doc_id)
                            have_sso = edxlogin_user.have_sso
                            doc_id = edxlogin_user.run
                    except User.DoesNotExist:
                        user_data = {
                            'email':dato[1],
                            'nombreCompleto':dato[0],
                            'pass': aux_pass
                        }
                        user = create_user_by_data(user_data, dato[1], True)
                    for course_id in course_ids:
                        enroll_in_course(user, course_id, enroll, mode)
                    lista_saved.append({
                        'email': dato[1],
                        'nombreCompleto': user.profile.name.strip(),
                        'doc_id': doc_id,
                        'password': aux_pass,
                        'sso': have_sso,
                        'exists': user_exists
                    })
        return lista_saved, lista_not_saved

    def get_or_create_user_with_doc_id(self, dato, aux_pass):
        """
        Get user data and create the user.
        """
        created = False
        if User.objects.filter(email=dato[1]).exists():
            user = User.objects.get(email=dato[1])
            doc_id = get_doc_id_by_user_id(user.id)
            if doc_id is not None:
                return None, created
            else:
                check_sso = check_doc_id_have_sso(dato[2])
                try:
                    edxlogin_user = create_edxloginuser(user, check_sso, dato[2])
                except:
                    logger.error(f"Can't create edxlogin_user for user: {user}.")
                    return None, False
        else:
            try:
                check_sso = check_doc_id_have_sso(dato[2])
            except Exception:
                check_sso = False
            with transaction.atomic():
                user_data = {
                    'email': dato[1],
                    'nombreCompleto': dato[0],
                    'pass': aux_pass
                }
                user = create_user_by_data(user_data, dato[1], True)
                try:
                    edxlogin_user = create_edxloginuser(user, check_sso, dato[2])
                except:
                    logger.error(f"Can't create edxlogin_user for user: {user}.")
                    return None, False
            created = True
        return edxlogin_user, created


class EdxLoginUserData(View):
    """
    Gives basic information on uchile users making queries to ph, given a list of doc_ids
    """
    def get(self, request):
        if check_permission_instructor_staff(request.user):
            context = {'doc_ids': ''}
            return render(request, 'edxlogin/userdata.html', context)
        else:
            raise Http404()

    def post(self, request):
        """
        Returns a CSV with the data for the requested users.
        """
        if check_permission_instructor_staff(request.user):
            doc_id_list = request.POST.get("doc_ids", "").split('\n')
            # doc_id clean up.
            doc_id_list = [doc_id.upper() for doc_id in doc_id_list]
            doc_id_list = [doc_id.replace("-", "") for doc_id in doc_id_list]
            doc_id_list = [doc_id.replace(".", "") for doc_id in doc_id_list]
            doc_id_list = [doc_id.strip() for doc_id in doc_id_list]
            doc_id_list = [doc_id for doc_id in doc_id_list if doc_id]

            context = {
                'doc_ids': request.POST.get('doc_ids')
            }
            # Data validation.
            invalid_doc_id_list = []
            for doc_id in doc_id_list:
                if not validate_all_doc_id_types(doc_id):
                    invalid_doc_id_list.append(doc_id)
            if invalid_doc_id_list:
                context["invalid_doc_ids"] = " - ".join(invalid_doc_id_list)
            # Returns if there is no input or if there is an invalid doc_id.
            if invalid_doc_id_list or not doc_id_list:
                return render(request, 'edxlogin/userdata.html', context)
            return self.export_data(doc_id_list)
        else:
            raise Http404()

    def export_data(self, doc_id_list):
        """
        Create the CSV.
        """
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'

        writer = csv.writer(
            response,
            delimiter=';',
            dialect='excel',
            encoding='utf-8')
        headers = ['Documento_id', 'Username', 'Apellido Paterno', 'Apellido Materno', 'Nombre', 'Email']
        writer.writerow(headers)
        for doc_id in doc_id_list:
            while len(doc_id) < 10 and 'P' != doc_id[0] and 'CG' != doc_id[0:2]:
                doc_id = "0" + doc_id
            try:
                user_data = get_user_data(doc_id, 'indiv_id')
            except Exception:
                user_data = {
                'doc_id': doc_id,
                'username': 'No Encontrado',
                'nombres': 'No Encontrado',
                'apellidoPaterno': 'No Encontrado',
                'apellidoMaterno': 'No Encontrado',
                'emails': ['No Encontrado']
            }
            data = [doc_id,
                    user_data['username'],
                    user_data['apellidoPaterno'],
                    user_data['apellidoMaterno'],
                    user_data['nombres']] + user_data['emails']
            writer.writerow(data)
        return response
    