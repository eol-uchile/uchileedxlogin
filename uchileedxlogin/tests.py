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
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from common.djangoapps.student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
import re
import json
import urllib.parse
import uuid
from .views import EdxLoginLoginRedirect, EdxLoginCallback, EdxLoginStaff
from .models import EdxLoginUserCourseRegistration, EdxLoginUser


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
            "http://testserver/uchileedxlogin/callback/?next=Lw==")

    def test_redirect_already_logged(self):
        """
            Test redirect when the user is already logged
        """
        user = User.objects.create_user(username='testuser', password='123')
        self.client.login(username='testuser', password='123')
        result = self.client.get(reverse('uchileedxlogin-login:login'))
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/')

class TestCallbackView(ModuleStoreTestCase):
    def setUp(self):
        super(TestCallbackView, self).setUp()
        self.client = Client()
        result = self.client.get(reverse('uchileedxlogin-login:login'))
        with patch('common.djangoapps.student.models.cc.User.save'):
            user = UserFactory(
                username='testuser3',
                password='12345',
                email='test555@test.test',
                is_staff=True)
            user2 = UserFactory(
                username='testuser22',
                password='12345',
                email='test22@test.test',
                is_staff=True)
        EdxLoginUser.objects.create(user=user, run='009472337K', have_sso=False)

    @patch('requests.get')
    def test_login_parameters(self, get):
        """
            Test normal process
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST.NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket',
                'next': 'aHR0cHM6Ly9lb2wudWNoaWxlLmNsLw=='})
        self.assertEqual(result.status_code, 302)
        username = get.call_args_list[1][1]['params'][0]
        self.assertEqual(
            get.call_args_list[0][0][0],
            settings.EDXLOGIN_RESULT_VALIDATE)
        self.assertEqual(username[1], '"test.name"')
        self.assertEqual(
            get.call_args_list[1][0][0],
            settings.EDXLOGIN_USER_INFO_URL)

    @patch('requests.get')
    def test_login_create_user(self, get):
        """
            Test create user normal process
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        edxlogin_user = EdxLoginUser.objects.get(run="0112223334")
        self.assertEqual(edxlogin_user.run, "0112223334")
        self.assertEqual(edxlogin_user.user.email, "test@test.test")

    @patch('requests.get')
    def test_login_create_user_email_exists(self, get):
        """
            Test create user normal process when email exists but rut params dont exists on db
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test22@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        edxlogin_user = EdxLoginUser.objects.get(run="0112223334")
        self.assertEqual(edxlogin_user.run, "0112223334")
        self.assertEqual(edxlogin_user.user.email, "test22@test.test")

    @patch('requests.get')
    def test_login_error_to_get_data(self, get):
        """
            Test create user when fail to get data from ph api
        """
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':None}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())

    @patch('requests.get')
    def test_login_error_to_get_data_2(self, get):
        """
            Test create user when fail to get data from ph api
        """
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code': 400,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())

    @patch('requests.get')
    def test_login_error_to_get_data_3(self, get):
        """
            Test create user when fail to get data from ph api
        """
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code': 400,'persona':[]}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())

    @patch('requests.get')
    def test_login_error_to_get_data_4(self, get):
        """
            Test create user when fail to get data from ph api
        """
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code': 400}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())

    @patch('requests.get')
    def test_login_update_have_sso_param(self, get):
        """
            Test callback update have_sso param
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                            namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "009472337K"}]}}})]
        edxlogin_user = EdxLoginUser.objects.get(run="009472337K")
        self.assertFalse(edxlogin_user.have_sso)
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        edxlogin_user = EdxLoginUser.objects.get(run="009472337K")
        self.assertEqual(edxlogin_user.run, "009472337K")
        self.assertTrue(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, "test555@test.test")

    @patch('requests.get')
    def test_login_create_user_wrong_email(self, get):
        """
            Test create user when email is wrong
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test'}],
                                                     "indiv_id": "0112223334"}]}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    @patch('requests.get')
    def test_login_create_user_email_diff_rut(self, get):
        """
            Test create user when email have different rut param
        """
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test555@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]


        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertFalse(EdxLoginUser.objects.filter(run="0112223334").exists())
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    @patch('requests.get')
    def test_login_wrong_ticket(self, get):
        """
            Test callback when ticket is wrong
        """
        # Assert requests.get calls
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('no\n\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'wrongticket'})
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    @patch('requests.get')
    def test_login_wrong_username(self, get):
        """
            Test callback when username is wrong
        """
        # Assert requests.get calls
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "content"])(
                200, ('yes\nwrongname\n').encode('utf-8')), 
            namedtuple("Request",
                ["status_code",
                "json"])(200,
                        lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[]}}})]
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        request = urllib.parse.urlparse(result.url)
        self.assertEqual(request.path, '/uchileedxlogin/login/')

    def test_generate_username(self):
        """
            Test callback generate username normal process
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'dd',
            'nombres': 'aa bb',
            'apellidoPaterno': 'cc',
            'rut': '0112223334',
            'email': 'null'
        }
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_cc')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_cc_d')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_cc_dd')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_b_cc')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_bb_cc')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_b_cc_d')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_b_cc_dd')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_bb_cc_d')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_bb_cc_dd')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_cc1')
        data['email'] =  str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            EdxLoginCallback().create_user_by_data(dict(data), False).username,
            'aa_cc2')

    def test_long_name(self):
        """
            Test callback generate username long name
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a2345678901234567890123 bb',
            'apellidoPaterno': '4567890',
            'rut': '0112223334',
            'email': 'test@test.test'
        }

        self.assertEqual(EdxLoginCallback().create_user_by_data(
            data, False).username, 'a2345678901234567890123_41')

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

    def test_whitespace_lastname(self):
        """
            Test callback generate username when lastname has too much whitespace
        """
        user_data = {
            "nombres": "Name",
            "apellidoPaterno": "          Last    Last2      ",
            "apellidoMaterno": '    Last2      '}
        self.assertEqual(
            EdxLoginCallback().generate_username(user_data),
            "Name_Last")

    def test_long_name_middle(self):
        """
            Test callback generate username when long name middle
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a23456789012345678901234 bb',
            'apellidoPaterno': '4567890',
            'rut': '0112223334',
            'email': 'test@test.test'
        }
        self.assertEqual(EdxLoginCallback().create_user_by_data(
            data, False).username, 'a234567890123456789012341')

    @patch('requests.get')
    def test_callback_enroll_pending_courses(self, get):
        """
            Test callback enroll when user have pending course with auto enroll and not auto enroll
        """
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2020',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        self.course_allowed = CourseFactory.create(
            org='mss',
            course='888',
            display_name='2019',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course_allowed.id)
        EdxLoginUserCourseRegistration.objects.create(
            run='0112223334',
            course=self.course.id,
            mode="honor",
            auto_enroll=True)
        EdxLoginUserCourseRegistration.objects.create(
            run='0112223334',
            course=self.course_allowed.id,
            mode="honor",
            auto_enroll=False)

        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "content"])(200,
                                                   ('yes\ntest.name\n').encode('utf-8')),
                           namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                    {"paterno": "TESTLASTNAME",
                                                     "materno": "TESTLASTNAME",
                                                     'pasaporte': [{'usuario':'username'}],
                                                     "nombres": "TEST NAME",
                                                     'email': [{'email': 'test@test.test'}],
                                                     "indiv_id": "0112223334"}]}}})]

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 2)
        result = self.client.get(
            reverse('uchileedxlogin-login:callback'),
            data={
                'ticket': 'testticket'})
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)

class TestStaffView(ModuleStoreTestCase):

    def setUp(self):
        super(TestStaffView, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2020',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        self.course2 = CourseFactory.create(
            org='mss',
            course='222',
            display_name='2021',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course2.id)
        self.course3 = CourseFactory.create(
            org='mss',
            course='333',
            display_name='2021',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course3.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
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
            role2 = CourseInstructorRole(self.course2.id)
            role.add_users(user_instructor)
            role2.add_users(user_instructor)
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
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course2.id)
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

    def test_staff_get_instructor_staff(self):
        """
            Test staff view, user with permission
        """
        response = self.instructor_staff_client.get(reverse('uchileedxlogin-login:staff'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
    
    def test_staff_get_anonymous_user(self):
        """
            Test staff view when user is anonymous
        """
        new_client = Client()
        response = new_client.get(reverse('uchileedxlogin-login:staff'))
        request = response.request
        self.assertEqual(response.status_code, 404)

    def test_staff_get_student_user(self):
        """
            Test staff view when user is student
        """
        response = self.student_client.get(reverse('uchileedxlogin-login:staff'))
        request = response.request
        self.assertEqual(response.status_code, 404)

    def test_staff_post(self):
        """
            Test staff view post normal process
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': str(self.course.id),
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
            'runs': '10-8\n9045578-8\n7193711-9\n19961161-5\n24902414-7',
            'course': str(self.course.id),
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        runs = ['0000000108','0090455788','0071937119','0199611615','0249024147']
        for run in runs:
            aux = EdxLoginUserCourseRegistration.objects.get(run=run)
            self.assertEqual(aux.run, run)
            self.assertEqual(aux.mode, 'audit')
            self.assertEqual(str(aux.course), str(self.course.id))
            self.assertEqual(aux.auto_enroll, True)

        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 5)

    def test_staff_post_multiple_run_multiple_course(self):
        """
            Test staff view post with multiple 'run' and multiple courses
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8\n9045578-8\n7193711-9\n19961161-5\n24902414-7',
            'course': '{}\n{}'.format(str(self.course.id),str(self.course2.id)),
            'modes': 'audit',
            'enroll': '1'
        }
        runs = ['0000000108','0090455788','0071937119','0199611615','0249024147']
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        for run in runs:
            aux = EdxLoginUserCourseRegistration.objects.get(run=run, course=self.course.id)
            self.assertEqual(aux.run, run)
            self.assertEqual(aux.mode, 'audit')
            self.assertEqual(str(aux.course), str(self.course.id))
            self.assertEqual(aux.auto_enroll, True)

        for run in runs:
            aux = EdxLoginUserCourseRegistration.objects.get(run=run, course=self.course2.id)
            self.assertEqual(aux.run, run)
            self.assertEqual(aux.mode, 'audit')
            self.assertEqual(str(aux.course), str(self.course2.id))
            self.assertEqual(aux.auto_enroll, True)

        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 10)

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

    def test_staff_post_duplicate_multiple_courses(self):
        """
            Test staff view post when course is duplicated in form
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': 'course-v1:tet+MSS001+2009_2\ncourse-v1:tet+MSS001+2009_2',
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"duplicate_courses\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_duplicate_multiple_ruts(self):
        """
            Test staff view post when ruts is duplicated in form
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8\n10-8\n10-8\n10-8\n10-8',
            'course': 'course-v1:tet+MSS001+2009_2',
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"duplicate_ruts\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_multiple_course_no_permission(self):
        """
            Test staff view post multiple course when user dont have permission
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': '{}\n{}'.format(str(self.course.id),str(self.course3.id)),
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client_instructor.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"error_permission\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_multiple_course_wrong_course(self):
        """
            Test staff view post multiple course when course is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': '{}\n{}'.format(str(self.course.id), 'course-v1:tet+MSS001+2009_2'),
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client_instructor.post(
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

    @patch('requests.get')
    def test_staff_post_force_enroll(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertEqual(edxlogin_user.user.email, "test@test.test")

    @patch('requests.get')
    def test_staff_post_force_enroll_uchile_email(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.cl'},{'email': 'test@test2.cl'},{'email': 'test@uchile.cl'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertEqual(edxlogin_user.user.email, "test@uchile.cl")

    @patch('requests.get')
    def test_staff_post_force_enroll_exists_email(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'student@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertEqual(edxlogin_user.user.email, "student@edx.org")

    @patch('requests.get')
    def test_staff_post_force_enroll_exists_email_2(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'student22@edx2.org'},{'email': 'student@uchile.cl'},{'email': 'student@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertEqual(edxlogin_user.user.email, "student@edx.org")

    @patch('requests.get')
    def test_staff_post_force_enroll_exists_email_3(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'student22@edx2.org'},{'email': 'student2@edx.org'},{'email': 'student55@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"run_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertTrue(edxlogin_user.user.email in ['student22@edx2.org', 'student55@edx.org'])

    @patch('requests.get')
    def test_staff_post_force_enroll_email_diff_rut(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'student2@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_2(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[]}}})]

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_3(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':400,'persona':[]}}})]

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_4(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':None}})]

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_5(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'runs': '10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "text"])(400,
            lambda:{})]

        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"run_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_no_enroll(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        request = response.request

        self.assertEqual(response.status_code, 200)
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 0)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/staff/')
        self.assertTrue("id=\"run_saved_force_no_auto\"" in response._container[0].decode())
        self.assertTrue(
            "id=\"run_saved_enroll_no_auto\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertEqual(edxlogin_user.user.email, "test@test.test")

    @patch('requests.get')
    def test_staff_post_force_no_user(self, get):
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

        get.side_effect = [namedtuple("Request", ["status_code"])(302)]
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

    @patch('requests.get')
    def test_staff_post_staff_course(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.staff_user_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUser.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
        r = json.loads(response._container[0].decode())
        self.assertEqual(r['run_saved']['run_saved_force'], "TEST_TESTLASTNAME - 0000000108")        
        self.assertEqual(aux.user.email, "test@test.test")

    @patch('requests.get')
    def test_staff_post_instructor_staff(self, get):
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

        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.instructor_staff_client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(not EdxLoginUser.objects.filter(run="0000000108").exists())
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_permission'], [str(self.course.id)])

    @patch('requests.get')
    def test_staff_post_instructor(self, get):
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
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client_instructor.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUser.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
        self.assertEqual(aux.user.email, "test@test.test")
        r = json.loads(response._container[0].decode())
        self.assertEqual(r['run_saved']['run_saved_force'], "TEST_TESTLASTNAME - 0000000108")

    @patch('requests.get')
    def test_staff_post_instructor_multiple_course(self, get):
        """
            Test staff view post when user is instructor and multiple course
        """
        post_data = {
            'action': "enroll",
            'runs': '10-8',
            'course': '{}\n{}'.format(str(self.course.id), str(self.course2.id)),
            'modes': 'audit',
            'enroll': '1',
            'force': '1'
        }
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]

        response = self.client_instructor.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUser.objects.get(run="0000000108")

        self.assertEqual(aux.run, "0000000108")
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)
        self.assertEqual(aux.user.email, "test@test.test")
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
        self.assertEqual(r['run_unenroll_no_exists'], ['0000000108'])

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
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['run_unenroll'], ['0000000108'])
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
        self.assertEqual(r['run_unenroll'], ['0000000108'])

    def test_staff_post_unenroll_enrollment_multiple_course(self):
        """
            Test staff view post unenroll when user have enrollment 
        """
        post_data = {
            'action': "unenroll",
            'runs': '10-8',
            'course': '{}\n{}'.format(str(self.course.id), str(self.course2.id)),
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['run_unenroll'], ['0000000108'])

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
        self.assertEqual(r['run_unenroll'], ['0000000108'])

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

    @patch('requests.get')
    def test_staff_post_enroll_student(self, get):
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
    
    def test_staff_post_passport(self):
        """
            Test staff view post normal process with passport
        """
        post_data = {
            'action': "staff_enroll",
            'runs': 'P12345',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUserCourseRegistration.objects.get(run="P12345")

        self.assertEqual(aux.run, "P12345")
        self.assertEqual(aux.mode, 'audit')
        self.assertEqual(aux.auto_enroll, True)
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 1)

    def test_staff_post_CG(self):
        """
            Test staff view post normal process with passport
        """
        post_data = {
            'action': "staff_enroll",
            'runs': 'CG12345678',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)

        aux = EdxLoginUserCourseRegistration.objects.get(run="CG12345678")

        self.assertEqual(aux.run, "CG12345678")
        self.assertEqual(aux.mode, 'audit')
        self.assertEqual(aux.auto_enroll, True)
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 1)

    def test_staff_post_wrong_passport(self):
        """
            Test staff view post when 'runs' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'runs': 'P213',
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

    def test_staff_post_wrong_CG(self):
        """
            Test staff view post when 'runs' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'runs': 'CG128',
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
    
class TestExternalView(ModuleStoreTestCase):
    def setUp(self):
        super(TestExternalView, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2020',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        self.course2 = CourseFactory.create(
            org='mss',
            course='222',
            display_name='2021',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course2.id)
        self.course3 = CourseFactory.create(
            org='mss',
            course='333',
            display_name='2021',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course3.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
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
            self.user_staff = user
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
            role2 = CourseInstructorRole(self.course2.id)
            role.add_users(user_instructor)
            role2.add_users(user_instructor)
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
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course2.id)
            self.assertTrue(
                self.student_client.login(
                    username='student',
                    password='12345'))

        EdxLoginUser.objects.create(user=user, run='009472337K')
        result = self.client.get(reverse('uchileedxlogin-login:external'))

    def test_external_get(self):
        """
            Test external view
        """
        response = self.client.get(reverse('uchileedxlogin-login:external'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/external/')

    def test_external_get_instructor_staff(self):
        """
            Test external view, user with permission
        """
        response = self.instructor_staff_client.get(reverse('uchileedxlogin-login:external'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/uchileedxlogin/external/')

    def test_external_get_anonymous_user(self):
        """
            Test external view when user is anonymous
        """
        new_client = Client()
        response = new_client.get(reverse('uchileedxlogin-login:external'))
        request = response.request
        self.assertEqual(response.status_code, 404)

    def test_external_get_student_user(self):
        """
            Test external view when user is student
        """
        response = self.student_client.get(reverse('uchileedxlogin-login:external'))
        request = response.request
        self.assertEqual(response.status_code, 404)

    def test_external_post_without_run(self):
        """
            Test external view post without run and email no exists in db platform
        """
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertFalse('id="action_send"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(email="aux.student2@edx.org").exists())

    def test_external_post_without_run_multiple_course(self):
        """
            Test external view post without run and email no exists in db platform with multiple course
        """
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org',
            'course': '{}\n{}'.format(str(self.course.id), str(self.course2.id)),
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertFalse('id="action_send"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(email="aux.student2@edx.org").exists())

    def test_external_post_without_run_exists_email(self):
        """
            Test external view post without run and email exists in db platform
        """
        post_data = {
            'datos': 'aa bb cc dd, student2@edx.org',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertTrue(User.objects.filter(email="student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())

    def test_external_post_without_run_exists_email_multiple_course(self):
        """
            Test external view post without run and email exists in db platform with multiple course
        """
        post_data = {
            'datos': 'aa bb cc dd, student2@edx.org',
            'course': '{}\n{}'.format(str(self.course.id), str(self.course2.id)),
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertTrue(User.objects.filter(email="student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())

    @patch('requests.get')
    def test_external_post_with_run(self, get):
        """
            Test external view post with run and (run,email) no exists in db platform
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "0000000108"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertFalse('id="action_send"' in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.user.email, "aux.student2@edx.org")

    @patch('requests.get')
    def test_external_post_with_passport(self, get):
        """
            Test external view post with passport and (run,email) no exists in db platform
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "P123465789"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org, P123465789',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertFalse('id="action_send"' in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="P123465789")
        self.assertEqual(edxlogin_user.user.email, "aux.student2@edx.org")

    @patch('requests.get')
    def test_external_post_with_passport_lower(self, get):
        """
            Test external view post with passport and (run,email) no exists in db platform
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test@test.test'}],
                  "indiv_id": "P123465789"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org, p123465789',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertFalse('id="action_send"' in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="P123465789")
        self.assertEqual(edxlogin_user.user.email, "aux.student2@edx.org")

    @patch('requests.get')
    def test_external_post_with_run_exists_email(self, get):
        """
            Test external view post with run,email exists, run no exists in db platform
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'student@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, student@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertTrue(User.objects.filter(email="student@edx.org").exists())
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.user.email, "student@edx.org")

    def test_external_post_with_exists_run(self):
        """
            Test external view post when run exists in db platform
        """
        post_data = {
            'datos': 'aa bb cc dd, student2@edx.org, 9472337-K',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())

    def test_external_post_without_run_multiple_data(self):
        """
            Test external view post without run, multiple data
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\naa bb cc dd, aux.student2@edx.org\nttttt rrrrr, aux.student3@edx.org',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student1@edx.org").exists())
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        self.assertFalse(User.objects.filter(email="aux.student3@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(email="aux.student1@edx.org").exists())
        self.assertTrue(User.objects.filter(email="aux.student2@edx.org").exists())
        self.assertTrue(User.objects.filter(email="aux.student3@edx.org").exists())

    def test_external_post_empty_data(self):
        """
            Test external view post without data
        """
        post_data = {
            'datos': '',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="no_data"' in response._container[0].decode())

    def test_external_post_empty_course(self):
        """
            Test external view post without course
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\n',
            'course': '',
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="curso2"' in response._container[0].decode())

    def test_external_post_wrong_course(self):
        """
            Test external view post with wrong course
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\n',
            'course': 'asdadsadsad',
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_curso"' in response._container[0].decode())
    
    def test_external_post_multiple_course_wrong_course(self):
        """
            Test external view post with wrong course
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\n',
            'course': '{}\n{}'.format(str(self.course.id), 'course-v1:tet+MSS001+2009_2'),
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_curso"' in response._container[0].decode())

    def test_external_post_multiple_course_no_permission(self):
        """
            Test external view post multiple course when user dont have permission
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\n',
            'course': '{}\n{}'.format(str(self.course.id),str(self.course3.id)),
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client_instructor.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_permission"' in response._container[0].decode())

    def test_external_post_course_not_exists(self):
        """
            Test external view post, course not exists
        """
        post_data = {
            'datos': 'gggggggg fffffff, aux.student1@edx.org\n',
            'course': 'course_v1:eol+test+2020',
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_curso"' in response._container[0].decode())

    def test_external_post_empty_mode(self):
        """
            Test external view post without mode
        """
        post_data = {
            'datos': 'asd asd, asd asd@ada.as',
            'course': self.course.id,
            'modes': '',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_mode"' in response._container[0].decode())

    def test_external_post_empty_name(self):
        """
            Test external view post without full name 
        """
        post_data = {
            'datos': ', asd@asad.cl',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="wrong_data"' in response._container[0].decode())

    def test_external_post_empty_email(self):
        """
            Test external view post without email
        """
        post_data = {
            'datos': 'adssad sadadas',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="wrong_data"' in response._container[0].decode())

    def test_external_post_wrong_run(self):
        """
            Test external view post with wrong run
        """
        post_data = {
            'datos': 'asdda sadsa, asd@asad.cl, 10-9',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="wrong_data"' in response._container[0].decode())

    def test_external_post_duplicate_multiple_run(self):
        """
            Test external view post with wrong run
        """
        post_data = {
            'datos': 'asdda sadsa, asd@asad.cl, 10-8\nasadsdda sadssda, asdq@aswad.cl, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="duplicate_rut"' in response._container[0].decode())

    def test_external_post_duplicate_multiple_email(self):
        """
            Test external view post with wrong run
        """
        post_data = {
            'datos': 'asdda sadsa, asd@asad.cl, 10-8\nasadsdda sadssda, asd@asad.cl, 9045578-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="duplicate_email"' in response._container[0].decode())

    def test_external_post_duplicate_multiple_course(self):
        """
            Test external view post with wrong run
        """
        post_data = {
            'datos': 'asdda sadsa, asd@asad.cl, 10-9',
            'course': '{}\n{}'.format(self.course.id, self.course.id),
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="duplicate_courses"' in response._container[0].decode())

    def test_external_post_wrong_email(self):
        """
            Test external view post with wrong email
        """
        post_data = {
            'datos': 'asdasd adsad, as$d_asd.asad.cl',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="wrong_data"' in response._container[0].decode())
        post_data = {
            'datos': 'asdasd adsad, ásasdñasd@asad.cl',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="wrong_data"' in response._container[0].decode())

    def test_external_post_one_name(self):
        """
            Test external view post when full name only have 1 word
        """
        post_data = {
            'datos': 'student, student1@student1.cl\n',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(email="student1@student1.cl").exists())

    def test_external_post_multiple_one_name(self):
        """
            Test external view post when full name only have 1 word and exists in db
        """
        post_data = {
            'datos': 'student, student2@student.cl\nstudent, student3@student.cl\nstudent, student4@student.cl\nstudent, student5@student.cl\n',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(username='student1', email="student2@student.cl").exists())
        self.assertTrue(User.objects.filter(username='student2', email="student3@student.cl").exists())
        self.assertTrue(User.objects.filter(username='student3', email="student4@student.cl").exists())
        self.assertTrue(User.objects.filter(username='student4', email="student5@student.cl").exists())

    def test_external_post_without_run_name_with_special_character_2(self):
        """
            Test external view post, name with special characters
        """
        post_data = {
            'datos': 'asd$asd ads#ad, adsertad@adsa.cl\nhola_ hola mundo mundo, hola@mundo.com',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="adsertad@adsa.cl").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        user_created = User.objects.get(email="adsertad@adsa.cl")
        user_created_2 = User.objects.get(email="hola@mundo.com")
        self.assertEqual(user_created_2.username, 'hola__mundo')

    def test_external_post_without_run_name_with_special_character(self):
        """
            Test external view post, name with special characters
        """
        post_data = {
            'datos': 'ニーア オートマタ íï-óö.úü , aux.student2@edx.org',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="aux.student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(User.objects.filter(email="aux.student2@edx.org").exists())

    def test_external_post_limit_data_exceeded(self):
        """
            Test external view post, limit data exceeded
        """
        datos = ""
        for a in range(55):
            datos = datos + "a\n"
        post_data = {
            'datos': datos,
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="limit_data"' in response._container[0].decode())

    def test_external_post_send_email(self):
        """
            Test external view post with send email
        """
        post_data = {
            'datos': 'aa bb cc dd, aux.student2@edx.org',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1',
            'send_email' : '1'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="action_send"' in response._container[0].decode())

    @patch('requests.get')
    def test_external_post_with_run_email_diff_rut(self, get):
        """
            Test external view post with run, when email already have anther rut params
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [{'usuario':'username'}],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'instructor_staff@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, student2@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertTrue(User.objects.filter(email="student2@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_not_saved"' in response._container[0].decode())
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_external_post_with_run_fail_get_data(self, get):
        """
            Test external view post with run, when fail to get data from ph api
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                 {"paterno": "TESTLASTNAME",
                  "materno": "TESTLASTNAME",
                  'pasaporte': [],
                  "nombres": "TEST NAME",
                  'email': [{'email': 'test2099@edx.org'}],
                  "indiv_id": "0000000108"}]}}})]
        post_data = {
            'datos': 'aa bb cc dd, test2099@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="test2099@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(EdxLoginUser.objects.filter(run="0000000108").exists())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertFalse(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, 'test2099@edx.org')

    @patch('requests.get')
    def test_external_post_with_run_fail_get_data_2(self, get):
        """
            Test external view post with run, when fail to get data from ph api
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[ ]}}})]
        post_data = {
            'datos': 'aa bb cc dd, test2099@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="test2099@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(EdxLoginUser.objects.filter(run="0000000108").exists())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertFalse(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, 'test2099@edx.org')

    @patch('requests.get')
    def test_external_post_with_run_fail_get_data_3(self, get):
        """
            Test external view post with run, when fail to get data from ph api
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':{'status_code':400,'persona':[ ]}}})]
        post_data = {
            'datos': 'aa bb cc dd, test2099@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="test2099@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(EdxLoginUser.objects.filter(run="0000000108").exists())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertFalse(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, 'test2099@edx.org')

    @patch('requests.get')
    def test_external_post_with_run_fail_get_data_4(self, get):
        """
            Test external view post with run, when fail to get data from ph api
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "json"])(200,
            lambda:{'data':{'getRowsPersona':None}})]
        post_data = {
            'datos': 'aa bb cc dd, test2099@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="test2099@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(EdxLoginUser.objects.filter(run="0000000108").exists())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertFalse(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, 'test2099@edx.org')

    @patch('requests.get')
    def test_external_post_with_run_fail_get_data_5(self, get):
        """
            Test external view post with run, when fail to get data from ph api
        """
        get.side_effect = [
            namedtuple("Request",
            ["status_code",
            "text"])(400,lambda:{})]
        post_data = {
            'datos': 'aa bb cc dd, test2099@edx.org, 10-8',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }
        self.assertFalse(User.objects.filter(email="test2099@edx.org").exists())
        response = self.client.post(
            reverse('uchileedxlogin-login:external'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="lista_saved"' in response._container[0].decode())
        self.assertTrue(EdxLoginUser.objects.filter(run="0000000108").exists())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertFalse(edxlogin_user.have_sso)
        self.assertEqual(edxlogin_user.user.email, 'test2099@edx.org')
