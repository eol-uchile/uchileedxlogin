#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.base import View
from django.http import HttpResponse
from .models import EdxLoginUser, EdxLoginUserCourseRegistration
from urllib.parse import urlencode
from itertools import cycle
from opaque_keys.edx.keys import CourseKey
from opaque_keys import InvalidKeyError
from courseware.courses import get_course_by_id, get_course_with_access
from courseware.access import has_access
from util.json_request import JsonResponse, JsonResponseBadRequest

import json
import requests
import uuid
import unidecode
import logging
import sys
import unicodecsv as csv
import re

logger = logging.getLogger(__name__)
regex = r'^(([^<>()\[\]\.,;:\s@\"]+(\.[^<>()\[\]\.,;:\s@\"]+)*)|(\".+\"))@(([^<>()[\]\.,;:\s@\"]+\.)+[^<>()[\]\.,;:\s@\"]{2,})$'


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


class Content(object):
    def get_user_data(self, username):
        """
        Get the user data
        """
        parameters = {
            'username': username
        }
        result = requests.get(
            settings.EDXLOGIN_USER_INFO_URL,
            params=urlencode(parameters),
            headers={
                'content-type': 'application/x-www-form-urlencoded',
                'User-Agent': 'curl/7.58.0'})
        if result.status_code != 200:
            logger.error(
                "{} {}".format(
                    result.request,
                    result.request.headers))
            raise Exception(
                "Wrong username {} {}".format(
                    result.status_code, username))
        return json.loads(result.text)

    def get_user_email(self, rut):
        """
        Get the user email
        """
        parameters = {
            'rut': rut
        }
        result = requests.post(
            settings.EDXLOGIN_USER_EMAIL,
            data=json.dumps(parameters),
            headers={
                'content-type': 'application/json'})
        if result.status_code == 200:
            data = json.loads(result.text)
            if 'emails' in data:
                return self.verify_email_principal(data)
        return 'null'

    def verify_email_principal(self, data):
        """
            Verify if data have principal email
        """
        for mail in data['emails']:
            if mail['nombreTipoEmail'] == 'PRINCIPAL':
                if mail['email'] is not None and re.match(
                        regex, mail['email'].lower()):
                    if not User.objects.filter(email=mail['email']).exists():
                        return mail['email']

        return self.verify_email_alternativo(data)

    def verify_email_alternativo(self, data):
        """
            Verify if data have alternative email
        """
        for mail in data['emails']:
            if mail['nombreTipoEmail'] == 'ALTERNATIVO':
                if mail['email'] is not None and re.match(
                        regex, mail['email'].lower()):
                    if not User.objects.filter(email=mail['email']).exists():
                        return mail['email']

        return 'null'

    def get_or_create_user(self, user_data):
        """
        Get or create the user given the user data.
        If the user exists, update the email address in case the users has updated it.
        """
        try:
            clave_user = EdxLoginUser.objects.get(run=user_data['rut'])
            return clave_user
        except EdxLoginUser.DoesNotExist:
            with transaction.atomic():
                user_data['email'] = self.get_user_email(user_data['rut'])
                user = self.create_user_by_data(user_data)
                edxlogin_user = EdxLoginUser.objects.create(
                    user=user,
                    run=user_data['rut']
                )
            return edxlogin_user

    def create_user_by_data(self, user_data):
        """
        Create the user by the Django model
        """
        from student.forms import AccountCreationForm
        from student.helpers import do_create_account

        # Check and remove email if its already registered

        if user_data['email'] == 'null':
            user_data['email'] = str(uuid.uuid4()) + '@invalid.invalid'

        form = AccountCreationForm(
            data={
                "username": self.generate_username(user_data),
                "email": user_data['email'],
                "password": "invalid",  # Temporary password
                "name": user_data['nombreCompleto'],
            },
            tos_required=False,
            ignore_email_blacklist=True
        )

        user, _, reg = do_create_account(form)
        reg.activate()
        reg.save()
        from student.models import create_comments_service_user
        create_comments_service_user(user)

        # Invalidate the user password, as it will be never be used
        user.set_unusable_password()
        user.save()

        return user

    def generate_username(self, user_data):
        """
        Generate an username for the given user_data
        This generation will be done as follow:
        1. return first_name[0] + "_" + last_name[0]
        2. return first_name[0] + "_" + last_name[0] + "_" + last_name[1..N][0..N]
        3. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[0]
        4. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[1..N][0..N]
        5. return first_name[0] + "_" + last_name[0] + N
        """
        aux_last_name = ((user_data['apellidoPaterno'] or '') +
                         " " + (user_data['apellidoMaterno'] or '')).strip()
        aux_last_name = aux_last_name.split(" ")
        aux_first_name = user_data['nombres'].split(" ")

        first_name = [
            unidecode.unidecode(x).replace(
                ' ', '_') for x in aux_first_name]
        last_name = [
            unidecode.unidecode(x).replace(
                ' ', '_') for x in aux_last_name]

        # 1.
        test_name = first_name[0] + "_" + last_name[0]
        if len(test_name) <= EdxLoginCallback.USERNAME_MAX_LENGTH and not User.objects.filter(
                username=test_name).exists():
            return test_name

        # 2.
        for i in range(len(last_name[1:])):
            test_name = test_name + "_"
            for j in range(len(last_name[i + 1])):
                test_name = test_name + last_name[i + 1][j]
                if len(test_name) > EdxLoginCallback.USERNAME_MAX_LENGTH:
                    break
                if not User.objects.filter(username=test_name).exists():
                    return test_name

        # 3.
        first_name_temp = first_name[0]
        for i in range(len(first_name[1:])):
            first_name_temp = first_name_temp + "_"
            for j in range(len(first_name[i + 1])):
                first_name_temp = first_name_temp + first_name[i + 1][j]
                test_name = first_name_temp + "_" + last_name[0]
                if len(test_name) > EdxLoginCallback.USERNAME_MAX_LENGTH:
                    break
                if not User.objects.filter(username=test_name).exists():
                    return test_name

        # 4.
        first_name_temp = first_name[0]
        for first_index in range(len(first_name[1:])):
            first_name_temp = first_name_temp + "_"
            for first_second_index in range(len(first_name[first_index + 1])):
                first_name_temp = first_name_temp + \
                    first_name[first_index + 1][first_second_index]
                test_name = first_name_temp + "_" + last_name[0]
                if len(test_name) > EdxLoginCallback.USERNAME_MAX_LENGTH:
                    break
                for second_index in range(len(last_name[1:])):
                    test_name = test_name + "_"
                    for second_second_index in range(
                            len(last_name[second_index + 1])):
                        test_name = test_name + \
                            last_name[second_index + 1][second_second_index]
                        if len(test_name) > EdxLoginCallback.USERNAME_MAX_LENGTH:
                            break
                        if not User.objects.filter(
                                username=test_name).exists():
                            return test_name

        # 5.
        # Make sure we have space to add the numbers in the username
        test_name = first_name[0] + "_" + last_name[0]
        test_name = test_name[0:(EdxLoginCallback.USERNAME_MAX_LENGTH - 5)]
        if test_name[-1] == '_':
            test_name = test_name[:-1]
        for i in range(1, 10000):
            name_tmp = test_name + str(i)
            if not User.objects.filter(username=name_tmp).exists():
                return name_tmp

        # Username cant be generated
        raise Exception("Error generating username for name {}".format())


class ContentStaff(object):
    def validarRut(self, rut):
        """
            Verify if the 'rut' is valid
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

    def validate_course(self, id_curso):
        """
            Verify if course.id exists
        """
        from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
        try:
            aux = CourseKey.from_string(id_curso)
            return CourseOverview.objects.filter(id=aux).exists()
        except InvalidKeyError:
            return False

    def validate_data(self, request, lista_run, context, force):
        """
            Verify if the data if valid
        """
        run_malos = ""
        # validacion de los run
        for run in lista_run:
            try:
                if run[0] == 'P':
                    if 5 > len(run[1:]) or len(run[1:]) > 20:
                        run_malos += run + " - "
                else:
                    if not self.validarRut(run):
                        run_malos += run + " - "

            except Exception:
                run_malos += run + " - "

        run_malos = run_malos[:-3]

        # validaciones de otros campos
        # si existe run malo
        if run_malos != "":
            context['run_malos'] = run_malos

        # valida curso
        if request.POST.get("course", "") == "":
            context['curso2'] = ''
        # valida si existe el curso
        elif not self.validate_course(request.POST.get("course", "")):
            context['error_curso'] = ''

        # si no se ingreso run
        if not lista_run:
            context['no_run'] = ''

        # si el modo es incorrecto
        if not request.POST.get(
                "modes", None) in [
                x[0] for x in EdxLoginUserCourseRegistration.MODE_CHOICES]:
            context['error_mode'] = ''

        # si la accion es incorrecto
        if not request.POST.get(
                "action",
                "") in [
                "enroll",
                "unenroll",
                "staff_enroll"]:
            context['error_action'] = ''
        return context

    def enroll_course(self, edxlogin_user, course, enroll, mode):
        """
        Enroll the user in the pending courses, removing the enrollments when
        they are applied.
        """
        from student.models import CourseEnrollment, CourseEnrollmentAllowed

        if enroll:
            CourseEnrollment.enroll(
                edxlogin_user.user,
                CourseKey.from_string(course),
                mode=mode)
        else:
            CourseEnrollmentAllowed.objects.create(
                course_id=CourseKey.from_string(course),
                email=edxlogin_user.user.email,
                user=edxlogin_user.user)

    def is_course_staff(self, request, course_id):
        """
            Verify if the user is staff course
        """
        try:
            course_key = CourseKey.from_string(course_id)
            course = get_course_with_access(request.user, "load", course_key)

            return bool(has_access(request.user, 'staff', course))
        except Exception:
            return False

    def is_instructor(self, request, course_id):
        """
            Verify if the user is instructor
        """
        try:
            course_key = CourseKey.from_string(course_id)
            course = get_course_with_access(request.user, "load", course_key)

            return bool(has_access(request.user, 'instructor', course))
        except Exception:
            return False

    def validate_user(self, request, course_id):
        """
            Verify if the user have permission
        """
        access = False
        if not request.user.is_anonymous:
            if request.user.has_perm('uchileedxlogin.uchile_instructor_staff'):
                if request.user.is_staff:
                    access = True
                if self.is_instructor(request, course_id):
                    access = True
                if self.is_course_staff(request, course_id):
                    access = True
        return access


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
        store the service parameter for uchileedxlogin.
        """

        parameters = {
            'service': EdxLoginLoginRedirect.get_callback_url(request),
            'renew': 'true'
        }
        return parameters

    @staticmethod
    def get_callback_url(request):
        """
        Get the callback url
        """
        import base64
        redirect_url = base64.b64encode(request.GET.get('next', "/").encode())
        url = request.build_absolute_uri(
            reverse('uchileedxlogin-login:callback'))
        return '{}?next={}'.format(url, redirect_url)


class EdxLoginCallback(View, Content):
    USERNAME_MAX_LENGTH = 30

    def get(self, request):
        import base64
        from openedx.core.djangoapps.user_authn.utils import is_safe_login_or_logout_redirect

        ticket = request.GET.get('ticket')
        redirect_url = base64.b64decode(
            request.GET.get(
                'next', "Lw==")).decode('utf-8')
        if not is_safe_login_or_logout_redirect(redirect_url, request.get_host(), None, False):
            redirect_url = "/"
        error_url = reverse('uchileedxlogin-login:login')

        if ticket is None:
            logger.exception("error ticket")
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
            self.login_user(request, username)
        except Exception:
            logger.exception("Error logging " + username + " - " + ticket)
            return HttpResponseRedirect(
                '{}?next={}'.format(
                    error_url, redirect_url))
        return HttpResponseRedirect(redirect_url)

    def verify_state(self, request, ticket):
        """
            Verify if the ticket is correct
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
            r = result.content.split('\n')
            if r[0] == 'yes':
                return r[1]

        return None

    def login_user(self, request, username):
        """
        Get or create the user and log him in.
        """
        user_data = self.get_user_data(username)
        user_data['username'] = username
        edxlogin_user = self.get_or_create_user(user_data)
        self.enroll_pending_courses(edxlogin_user)
        if request.user.is_anonymous or request.user.id != edxlogin_user.user.id:
            logout(request)
            login(
                request,
                edxlogin_user.user,
                backend="django.contrib.auth.backends.AllowAllUsersModelBackend",
            )

    def enroll_pending_courses(self, edxlogin_user):
        """
        Enroll the user in the pending courses, removing the enrollments when
        they are applied.
        """
        from student.models import CourseEnrollment, CourseEnrollmentAllowed
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


class EdxLoginStaff(View, Content, ContentStaff):
    """
        Enroll/force enroll/unenroll user
    """
    def get(self, request):
        course_id = request.GET.get("course", "")
        if self.validate_user(request, course_id):
            context = {'runs': '', 'auto_enroll': True, 'modo': 'audit'}
            return render(request, 'edxlogin/staff.html', context)
        else:
            raise Http404()

    @require_post_action()
    def post(self, request):
        course_id = request.POST.get("course", "")
        if self.validate_user(request, course_id):
            action = request.POST.get("action", "")
            lista_run = request.POST.get("runs", "").split('\n')
            # limpieza de los run ingresados
            lista_run = [run.upper() for run in lista_run]
            lista_run = [run.replace("-", "") for run in lista_run]
            lista_run = [run.replace(".", "") for run in lista_run]
            lista_run = [run.strip() for run in lista_run]
            lista_run = [run for run in lista_run if run]

            # verifica si el checkbox de auto enroll fue seleccionado
            enroll = False
            if request.POST.getlist("enroll"):
                enroll = True

            # verifica si el checkbox de forzar creacion de usuario fue
            # seleccionado
            force = False
            if request.POST.getlist("force"):
                force = True

            context = {
                'runs': request.POST.get('runs'),
                'curso': request.POST.get(
                    "course",
                    ""),
                'auto_enroll': enroll,
                'modo': request.POST.get(
                    "modes",
                    None)}
            # validacion de datos
            context = self.validate_data(request, lista_run, context, force)
            # retorna si hubo al menos un error
            if len(context) > 4 and action not in ["enroll", "unenroll"]:
                return render(request, 'edxlogin/staff.html', context)
            if len(context) > 4 and action in ["enroll", "unenroll"]:
                return JsonResponse(context)

            if action in ["enroll", "staff_enroll"]:
                context = self.enroll_or_create_user(
                    request, lista_run, force, enroll)
                if action in ["enroll"]:
                    return JsonResponse(context)
                return render(request, 'edxlogin/staff.html', context)

            elif action == "unenroll":
                context = self.unenroll_user(request, lista_run)
                return JsonResponse(context)
        else:
            raise Http404()

    def enroll_or_create_user(self, request, lista_run, force, enroll):
        """
            Enroll/force enroll users
        """
        run_saved_force = ""
        run_saved_force_no_auto = ""
        run_saved_pending = ""
        run_saved_enroll = ""
        run_saved_enroll_no_auto = ""
        # guarda el form
        with transaction.atomic():
            for run in lista_run:
                while len(run) < 10 and 'P' != run[0]:
                    run = "0" + run
                try:
                    edxlogin_user = EdxLoginUser.objects.get(run=run)
                    self.enroll_course(
                        edxlogin_user, request.POST.get(
                            "course", ""), enroll, request.POST.get(
                            "modes", None))
                    if enroll:
                        run_saved_enroll += edxlogin_user.user.username + " - " + run + " / "
                    else:
                        run_saved_enroll_no_auto += edxlogin_user.user.username + " - " + run + " / "
                except EdxLoginUser.DoesNotExist:
                    edxlogin_user = None
                    if force:
                        edxlogin_user = self.force_create_user(run)
                    if edxlogin_user:
                        self.enroll_course(
                            edxlogin_user, request.POST.get(
                                "course", ""), enroll, request.POST.get(
                                "modes", None))
                        if enroll:
                            run_saved_force += edxlogin_user.user.username + " - " + run + " / "
                        else:
                            run_saved_force_no_auto += edxlogin_user.user.username + " - " + run + " / "
                    else:
                        registro = EdxLoginUserCourseRegistration()
                        registro.run = run
                        registro.course = request.POST.get("course", "")
                        registro.mode = request.POST.get("modes", None)
                        registro.auto_enroll = enroll
                        registro.save()
                        run_saved_pending += run + " - "
        run_saved = {
            'run_saved_force': run_saved_force[:-3],
            'run_saved_pending': run_saved_pending[:-3],
            'run_saved_enroll': run_saved_enroll[:-3],
            'run_saved_enroll_no_auto': run_saved_enroll_no_auto[:-3],
            'run_saved_force_no_auto': run_saved_force_no_auto[:-3]
        }
        return {
            'runs': '',
            'auto_enroll': True,
            'modo': 'audit',
            'saved': 'saved',
            'run_saved': run_saved}

    def unenroll_user(self, request, lista_run):
        """
            Unenroll user
        """
        from student.models import CourseEnrollment, CourseEnrollmentAllowed

        run_unenroll_pending = ""
        run_unenroll_enroll = ""
        run_unenroll_enroll_allowed = ""
        run_no_exists = ""

        course_id = request.POST.get("course", "")
        course_key = CourseKey.from_string(course_id)
        with transaction.atomic():
            for run in lista_run:
                while len(run) < 10 and 'P' != run[0]:
                    run = "0" + run
                try:
                    edxlogin_user = EdxLoginUser.objects.get(run=run)

                    registrations = EdxLoginUserCourseRegistration.objects.filter(
                        run=run, course=course_key)
                    if registrations:
                        run_unenroll_pending += edxlogin_user.user.username + " - " + run + " / "
                        registrations.delete()

                    enrollmentAllowed = CourseEnrollmentAllowed.objects.filter(
                        course_id=course_key, user=edxlogin_user.user)
                    if enrollmentAllowed:
                        run_unenroll_enroll_allowed += edxlogin_user.user.username + " - " + run + " / "
                        enrollmentAllowed.delete()

                    enrollment = CourseEnrollment.get_enrollment(
                        edxlogin_user.user, course_key)
                    enrollment.is_active = 0
                    if enrollment:
                        run_unenroll_enroll += edxlogin_user.user.username + " - " + run + " / "
                        enrollment.save()

                except EdxLoginUser.DoesNotExist:
                    registrations = EdxLoginUserCourseRegistration.objects.filter(
                        run=run, course=course_key)
                    if registrations:
                        run_unenroll_pending += " No Registrado - " + run + " / "
                        registrations.delete()
                    else:
                        run_no_exists += run + " - "

        run_unenroll = {
            'run_unenroll_pending': run_unenroll_pending[:-3],
            'run_unenroll_enroll': run_unenroll_enroll[:-3],
            'run_unenroll_enroll_allowed': run_unenroll_enroll_allowed[:-3],
            'run_no_exists': run_no_exists[:-3],
        }
        return {
            'runs': '',
            'auto_enroll': True,
            'modo': 'honor',
            'saved': 'unenroll',
            'run_unenroll': run_unenroll}

    def force_create_user(self, run):
        """
            Get user data and create the user
        """
        try:
            username = self.get_username(run)
            user_data = self.get_user_data(username)
            user_data['username'] = username
            edxlogin_user = self.get_or_create_user(user_data)
            return edxlogin_user
        except Exception:
            return None

    def get_username(self, run):
        """
        Get username
        """

        parameters = {
            'rutUsuario': run
        }
        result = requests.post(
            settings.EDXLOGIN_USERNAME,
            data=json.dumps(parameters),
            headers={
                'content-type': 'application/json'})
        if result.status_code != 200:
            logger.error(
                "{} {}".format(
                    result.request,
                    result.request.headers))
            raise Exception("Wrong run {} {}".format(result.status_code, run))

        data = json.loads(result.text)
        username = ""
        if "cuentascorp" in data and len(data["cuentascorp"]) > 0:
            email = data["cuentascorp"]
            for name in email:
                if name["tipoCuenta"] == "CUENTA PASAPORTE":
                    username = name["cuentaCorp"] or ""
                    break
        return username


class EdxLoginExport(View):
    """
        Export all edxlogin users to csv file
    """

    def get(self, request):
        data = []
        users_edxlogin = EdxLoginUser.objects.all().order_by(
            'user__username').values('run', 'user__username', 'user__email')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'

        writer = csv.writer(
            response,
            delimiter=';',
            dialect='excel',
            encoding='utf-8')
        data.append([])
        data[0].extend(['Run', 'Username', 'Email'])
        i = 1
        for user in users_edxlogin:
            data.append([])
            data[i].extend(
                [user['run'], user['user__username'], user['user__email']])
            i += 1
        writer.writerows(data)

        return response
