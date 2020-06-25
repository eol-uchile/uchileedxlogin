#!/usr/bin/env python
# -*- coding: utf-8 -*-
from mock import patch, Mock, MagicMock
from collections import namedtuple
from django.urls import reverse
from django.test import TestCase, Client
from django.test import Client
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from urllib.parse import parse_qs
from opaque_keys.edx.locator import CourseLocator
from student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from student.roles import CourseInstructorRole, CourseStaffRole
import re
import json
import urllib.parse

from .views import EdxLoginLoginRedirect, EdxLoginCallback, EdxLoginStaff
from .models import EdxLoginUserCourseRegistration, EdxLoginUser
# Create your tests here.


class TestRedirectView(TestCase):

    def setUp(self):
        self.client = Client()

    def test_set_session(self):
        result = self.client.get(reverse('uchileedxlogin-login:login'))
        self.assertEqual(result.status_code, 302)

    def test_return_request(self):
        """
            Test if return request is correct
        """
        result = self.client.get(reverse('uchileedxlogin-login:login'))
        request = urllib.parse.urlparse(result.url)
        args = urllib.parse.parse_qs(request.query)

        self.assertEqual(result.status_code, 302)
        self.assertEqual(request.netloc, '172.25.14.193:9513')
        self.assertEqual(request.path, '/login')
        self.assertEqual(
            args['service'][0],
            "http://testserver/uchileedxlogin/callback/?next=b'Lw=='")

    def test_redirect_already_logged(self):
        """
            Test redirect when the user is already logged
        """
        user = User.objects.create_user(username='testuser', password='123')
        self.client.login(username='testuser', password='123')
        result = self.client.get(reverse('uchileedxlogin-login:login'))
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/')


def create_user(user_data):
    return User.objects.create_user(
        username=EdxLoginCallback().generate_username(user_data),
        email=user_data['email'])


def create_user2(user_data):
    return User.objects.create_user(
        username=EdxLoginStaff().generate_username(user_data),
        email=user_data['email'])


class TestCallbackView(TestCase):
    def setUp(self):
        self.client = Client()
        result = self.client.get(reverse('uchileedxlogin-login:login'))

        self.modules = {
            'student': MagicMock(),
            'student.forms': MagicMock(),
            'student.helpers': MagicMock(),
            'student.models': MagicMock(),
        }
        self.module_patcher = patch.dict('sys.modules', self.modules)
        self.module_patcher.start()

    def tearDown(self):
        self.module_patcher.stop()

    @patch('requests.post')
    @patch('requests.get')
    def test_login_parameters(self, get, post):
        """
            Test normal process
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST.NAME",
                                                            "nombreCompleto": "TEST.NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket',
                'next': 'aHR0cHM6Ly9lb2wudWNoaWxlLmNsLw=='})
        self.assertEqual(result.status_code, 302)

        username = parse_qs(get.call_args_list[1][1]['params'])
        self.assertEqual(
            get.call_args_list[0][0][0],
            settings.EDXLOGIN_RESULT_VALIDATE)
        self.assertEqual(username['username'][0], 'test.name')
        self.assertEqual(
            get.call_args_list[1][0][0],
            settings.EDXLOGIN_USER_INFO_URL)
        self.assertEqual(
            post.call_args_list[0][0][0],
            settings.EDXLOGIN_USER_EMAIL)

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user(self, get, post, mock_created_user):
        """
            Test create user normal process
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_no_email(self, get, post, mock_created_user):
        """
            Test create user when email is empty
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request", ["status_code", "text"])(
            200, json.dumps({'data': 'algo'}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'null'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_wrong_email(self, get, post, mock_created_user):
        """
            Test create user when email is wrong
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "sin@correo",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'null'})
    
    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_fail_email_404(self, get, post, mock_created_user):
        """
            Test create user when get email fail
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(404,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "sin@correo",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'null'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_null_email(self, get, post, mock_created_user):
        """
            Test create user when email is Null
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request", ["status_code", "text"])(200, json.dumps({"emails": [
            {"rut": "0112223334", "email": None, "codigoTipoEmail": "1", "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'null'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_wrong_email_principal(
            self, get, post, mock_created_user):
        """
            Test create user when principal email is wrong
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "sin@correo",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"},
                                                                        {"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "ALTERNATIVO"}]}))]

        self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_no_email_principal(
            self, get, post, mock_created_user):
        """
            Test create user when principal email is empty
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "ALTERNATIVO"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch('requests.post')
    @patch('requests.get')
    def test_login_create_user_no_email_alternativo(
            self, get, post, mock_created_user):
        """
            Test create user when email is empty
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request", ["status_code", "text"])(
            200, json.dumps({"emails": []}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'test.name',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0112223334',
                'email': 'null'})

    @patch('requests.post')
    @patch('requests.get')
    def test_login_wrong_ticket(self, get, post):
        """
            Test callback when ticket is wrong
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'no\n\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'wrongticket'})
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    @patch('requests.post')
    @patch('requests.get')
    def test_login_wrong_username(self, get, post):
        """
            Test callback when username is wrong
        """
        # Assert requests.get calls
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "content"])(
                200, 'yes\nwrongname\n'), namedtuple(
                    "Request", [
                        "status_code", "text"])(
                            200, json.dumps(
                                {}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    def test_generate_username(self, _):
        """
            Test callback generate username normal process
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'dd',
            'nombres': 'aa bb',
            'apellidoPaterno': 'cc',
            'nombreCompleto': 'aa bb cc dd',
            'rut': '0112223334',
            'email': 'test@test.test'
        }
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_cc')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_cc_d')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_cc_dd')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_b_cc')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_bb_cc')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_b_cc_d')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_b_cc_dd')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_bb_cc_d')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_bb_cc_dd')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_cc1')
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(data).username,
            'aa_cc2')

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    def test_long_name(self, _):
        """
            Test callback generate username long name
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a2345678901234567890123 bb',
            'apellidoPaterno': '4567890',
            'nombreCompleto': 'a2345678901234567890123 bb 4567890 ff',
            'rut': '0112223334',
            'email': 'test@test.test'
        }

        self.assertEqual(EdxLoginCallback().create_user_by_data(
            data).username, 'a2345678901234567890123_41')

    def test_null_lastname(self):
        """
            Test callback generate username when lastname is null
        """
        user_data = {
            "nombres": "Name",
            "apellidoPaterno": None,
            "apellidoMaterno": None}
        self.assertEqual(
            EdxLoginCallback().generate_username(user_data),
            "Name_")

        user_data = {
            "nombres": "Name",
            "apellidoPaterno": "Last",
            "apellidoMaterno": None}
        self.assertEqual(
            EdxLoginCallback().generate_username(user_data),
            "Name_Last")

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    def test_long_name_middle(self, _):
        """
            Test callback generate username when long name middle
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a23456789012345678901234 bb',
            'apellidoPaterno': '4567890',
            'nombreCompleto': 'a23456789012345678901234 bb 4567890 ff',
            'rut': '0112223334',
            'email': 'test@test.test'
        }
        self.assertEqual(EdxLoginCallback().create_user_by_data(
            data).username, 'a234567890123456789012341')

    @patch(
        "uchileedxlogin.views.EdxLoginCallback.create_user_by_data",
        side_effect=create_user)
    @patch("requests.post")
    @patch('requests.get')
    def test_test(self, get, post, _):
        """
            Test callback enroll when user have pending course with auto enroll and not auto enroll
        """
        EdxLoginUserCourseRegistration.objects.create(
            run='0112223334',
            course="course-v1:test+TEST+2019-2",
            mode="honor",
            auto_enroll=True)
        EdxLoginUserCourseRegistration.objects.create(
            run='0112223334',
            course="course-v1:test+TEST+2019-4",
            mode="honor",
            auto_enroll=False)

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   'yes\ntest.name\n'),
                           namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST.NAME",
                                                            "nombreCompleto": "TEST.NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0112223334"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0112223334",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(
            self.modules['student.models'].CourseEnrollment.method_calls[0][1][1],
            CourseLocator.from_string("course-v1:test+TEST+2019-2"))
        _, _, kwargs = self.modules['student.models'].CourseEnrollmentAllowed.mock_calls[0]
        self.assertEqual(
            kwargs['course_id'],
            CourseLocator.from_string("course-v1:test+TEST+2019-4"))


class TestStaffView(ModuleStoreTestCase):

    def setUp(self):
        super(TestStaffView, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2020',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        with patch('student.models.cc.User.save'):
            content_type = ContentType.objects.get_for_model(EdxLoginUser)
            permission = Permission.objects.get(
                codename='uchile_instructor_staff',
                content_type=content_type,
            )
            # staff user
            self.client = Client()
            user = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            user.user_permissions.add(permission)
            self.client.login(username='testuser3', password='12345')

            # user instructor
            self.client_instructor = Client()
            user_instructor = UserFactory(
                username='instructor',
                password='12345',
                email='instructor@edx.org')
            user_instructor.user_permissions.add(permission)
            role = CourseInstructorRole(self.course.id)
            role.add_users(user_instructor)
            self.client_instructor.login(
                username='instructor', password='12345')

            # user instructor staff
            self.instructor_staff = UserFactory(
                username='instructor_staff',
                password='12345',
                email='instructor_staff@edx.org')
            self.instructor_staff.user_permissions.add(permission)
            self.instructor_staff_client = Client()
            self.assertTrue(
                self.instructor_staff_client.login(
                    username='instructor_staff',
                    password='12345'))

            # user staff course
            self.staff_user_client = Client()
            self.staff_user = UserFactory(
                username='staff_user',
                password='12345',
                email='staff_user@edx.org')
            self.staff_user.user_permissions.add(permission)
            CourseEnrollmentFactory(
                user=self.staff_user,
                course_id=self.course.id)
            CourseStaffRole(self.course.id).add_users(self.staff_user)
            self.assertTrue(
                self.staff_user_client.login(
                    username='staff_user',
                    password='12345'))

            # user student
            self.student_client = Client()
            self.student = UserFactory(
                username='student',
                password='12345',
                email='student@edx.org')
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id)
            self.assertTrue(
                self.student_client.login(
                    username='student',
                    password='12345'))

        EdxLoginUser.objects.create(user=user, run='009472337K')
        result = self.client.get(reverse('uchileedxlogin-login:staff'))

    def test_staff_get(self):
        """
            Test staff view
        """
        response = self.client.get(reverse('uchileedxlogin-login:staff'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')

    def test_staff_post(self):
        """
            Test staff view post normal process
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUserCourseRegistration.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(aux.mode, 'audit')
        self.assertEqual(aux.auto_enroll, True)
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 1)

    def test_staff_post_multiple_run(self):
        """
            Test staff view post with multiple 'run'
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8\n10-8\n10-8\n10-8\n10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUserCourseRegistration.objects.filter(run="0000000108")
        for var in aux:
            self.assertEqual(var.run, "0000000108")
            self.assertEqual(var.mode, 'audit')
            self.assertEqual(var.auto_enroll, True)

        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 5)

    def test_staff_post_sin_curso(self):
        """
            Test staff view post when course is empty
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': '',
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"curso2\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
    
    def test_staff_post_wrong_course(self):
        """
            Test staff view post when course is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': 'course-v1:tet+MSS001+2009_2',
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"error_curso\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_sin_run(self):
        """
            Test staff view post when 'runs' is empty
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"no_run\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_run_malo(self):
        """
            Test staff view post when 'runs' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '12345678-9',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"run_malos\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_exits_user_enroll(self):
        """
            Test staff view post with auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '9472337-k',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_enroll\"" in response._container[0].decode())

    def test_staff_post_exits_user_no_enroll(self):
        """
            Test staff view post without auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '9472337-k',
            'course': self.course.id,
            'modes': 'audit'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue(
            "id=\"run_saved_enroll_no_auto\"" in response._container[0].decode())

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_force_enroll(self, get, post, mock_created_user):
        """
            Test staff view post with force enroll normal process
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }
        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"},
                                {"cuentaCorp": "avilio.perez",
                                 "tipoCuenta": "CUENTA PASAPORTE",
                                 "organismoDominio": "Universidad de Chile"}]}

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0000000108"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps(data)),
                            namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0000000108",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'avilio.perez',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0000000108',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_force_no_enroll(self, get, post, mock_created_user):
        """
            Test staff view post with force enroll without auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'force': '1'
        }

        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"},
                                {"cuentaCorp": "avilio.perez",
                                 "tipoCuenta": "CUENTA PASAPORTE",
                                 "organismoDominio": "Universidad de Chile"}]}

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0000000108"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps(data)),
                            namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0000000108",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force_no_auto\"" in response._container[0].decode())
        self.assertTrue(
            "id=\"run_saved_enroll_no_auto\"" not in response._container[0].decode())
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'avilio.perez',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0000000108',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_force_no_user(self, get, post, mock_created_user):
        """
            Test staff view post with force enroll when fail get username
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"}]}

        get.side_effect = [namedtuple("Request", ["status_code"])(302)]
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "text"])(
                200, json.dumps(data)), namedtuple(
                    "Request", ["status_code"])(302)]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        aux = EdxLoginUserCourseRegistration.objects.get(run="0000000108")

        self.assertEqual(aux.run, '0000000108')
        self.assertEqual(aux.auto_enroll, True)
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 1)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())

    def test_staff_post_no_action_params(self):
        """
            Test staff view post without action
        """
        post_data = {
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(r['parameters'], ["action"])
        self.assertEqual(r['info'], {"action": ""})

    def test_staff_post_wrong_action_params(self):
        """
            Test staff view post with wrong action 
        """
        post_data = {
            'action': "test",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(r['parameters'], ["action"])
        self.assertEqual(r['info'], {"action": "test"})

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_staff_course(self, get, post, mock_created_user):
        """
            Test staff view post when user is staff course
        """
        post_data = {
            'action': "enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }
        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"},
                                {"cuentaCorp": "avilio.perez",
                                 "tipoCuenta": "CUENTA PASAPORTE",
                                 "organismoDominio": "Universidad de Chile"}]}

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0000000108"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps(data)),
                            namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0000000108",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        response = self.staff_user_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUser.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
        r = json.loads(response._container[0].decode())
        self.assertEqual(r['run_saved']['run_saved_force'], "TEST_TESTLASTNAME - 0000000108")
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'avilio.perez',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0000000108',
                'email': 'test@test.test'})

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_instructor_staff(self, get, post, mock_created_user):
        """
            Test staff view post when user have permission
        """
        post_data = {
            'action': "enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"},
                                {"cuentaCorp": "avilio.perez",
                                 "tipoCuenta": "CUENTA PASAPORTE",
                                 "organismoDominio": "Universidad de Chile"}]}

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0000000108"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps(data)),
                            namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0000000108",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        response = self.instructor_staff_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 404)

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_instructor(self, get, post, mock_created_user):
        """
            Test staff view post when user is instructor
        """
        post_data = {
            'action': "enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }
        data = {"cuentascorp": [{"cuentaCorp": "avilio.perez@ug.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "ug.uchile.cl"},
                                {"cuentaCorp": "avilio.perez@uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "uchile.cl"},
                                {"cuentaCorp": "avilio.perez@u.uchile.cl",
                                 "tipoCuenta": "EMAIL",
                                 "organismoDominio": "u.uchile.cl"},
                                {"cuentaCorp": "avilio.perez",
                                 "tipoCuenta": "CUENTA PASAPORTE",
                                 "organismoDominio": "Universidad de Chile"}]}

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "text"])(200,
                                                json.dumps({"apellidoPaterno": "TESTLASTNAME",
                                                            "apellidoMaterno": "TESTLASTNAME",
                                                            "nombres": "TEST NAME",
                                                            "nombreCompleto": "TEST NAME TESTLASTNAME TESTLASTNAME",
                                                            "rut": "0000000108"}))]
        post.side_effect = [namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps(data)),
                            namedtuple("Request",
                                       ["status_code",
                                        "text"])(200,
                                                 json.dumps({"emails": [{"rut": "0000000108",
                                                                         "email": "test@test.test",
                                                                         "codigoTipoEmail": "1",
                                                                         "nombreTipoEmail": "PRINCIPAL"}]}))]

        response = self.client_instructor.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUser.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
        self.assertEqual(
            mock_created_user.call_args_list[0][0][0],
            {
                'username': 'avilio.perez',
                'apellidoMaterno': 'TESTLASTNAME',
                'nombres': 'TEST NAME',
                'apellidoPaterno': 'TESTLASTNAME',
                'nombreCompleto': 'TEST NAME TESTLASTNAME TESTLASTNAME',
                'rut': '0000000108',
                'email': 'test@test.test'})
        r = json.loads(response._container[0].decode())
        self.assertEqual(r['run_saved']['run_saved_force'], "TEST_TESTLASTNAME - 0000000108")

    def test_staff_post_unenroll_no_db(self):
        """
            Test staff view post unenroll when user no exists
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['run_unenroll']['run_no_exists'], '0000000108')

    def test_staff_post_unenroll_edxlogincourse(self):
        """
            Test staff view post unenroll when user have edxlogincourse 
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        EdxLoginUserCourseRegistration.objects.create(
            run='0000000108',
            course=self.course.id,
            mode="audit",
            auto_enroll=True)

        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 1)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_unenroll_enrollment(self):
        """
            Test staff view post unenroll when user have enrollment 
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            r['run_unenroll']['run_unenroll_enroll'],
            'student - 0000000108')

    def test_staff_post_unenroll_allowed(self):
        """
            Test staff view post unenroll when user have CourseEnrollmentAllowed 
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        allowed = CourseEnrollmentAllowedFactory(
            email=self.student.email,
            course_id=self.course.id,
            user=self.student)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            r['run_unenroll']['run_unenroll_enroll_allowed'],
            'student - 0000000108')

    def test_staff_post_unenroll_student(self):
        """
            Test staff view post unenroll when user is student 
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')

        response = self.student_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 404)

    @patch(
        "uchileedxlogin.views.EdxLoginStaff.create_user_by_data",
        side_effect=create_user2)
    @patch('requests.post')
    @patch('requests.get')
    def test_staff_post_enroll_student(self, get, post, mock_created_user):
        """
            Test staff view post enroll when user is student 
        """
        post_data = {
            'action': "enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')

        response = self.student_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 404)
