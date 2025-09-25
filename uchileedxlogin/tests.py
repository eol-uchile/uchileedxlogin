#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Python Standard Libraries
import json
import urllib.parse
import uuid
from collections import namedtuple


# Installed packages (via pip)
from common.djangoapps.student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, Client
from django.urls import reverse
from mock import patch

# Edx dependencies
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

# Internal project dependencies
from .users import create_edxloginuser, create_user_by_data
from .models import EdxLoginUserCourseRegistration, EdxLoginUser
from .services.utils import get_document_type
from .utils import generate_username, get_user_from_emails, select_email, validate_all_doc_id_types, validate_rut


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
            Test create user normal process when email exists but doc_id params dont exists on db
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
    def test_login_create_user_email_diff_doc_id(self, get):
        """
            Test create user when email have different doc_id param
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
            Test generate username normal process
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'dd',
            'nombres': 'aa bb',
            'apellidoPaterno': 'cc',
            'doc_id': '0112223334',
            'email': 'null'
        }
        email = str(uuid.uuid4()) + '@invalid.invalid'
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_cc')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_cc_d')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_cc_dd')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_b_cc')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_bb_cc')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_b_cc_d')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_b_cc_dd')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_bb_cc_d')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_bb_cc_dd')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_cc1')
        self.assertEqual(
            create_user_by_data(dict(data), str(uuid.uuid4()) + '@invalid.invalid', False).username,
            'aa_cc2')

    def test_long_name(self):
        """
            Test generate username long name
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a2345678901234567890123 bb',
            'apellidoPaterno': '4567890',
            'doc_id': '0112223334',
            'email': 'test@test.test'
        }

        self.assertEqual(create_user_by_data(
            data, 'test@test.test', False).username, 'a2345678901234567890123_41')

    def test_null_lastname(self):
        """
            Test generate username when lastname is null
        """
        user_data = {
            "nombres": "Name",
            "apellidoPaterno": None,
            "apellidoMaterno": None}
        self.assertEqual(
            generate_username(user_data),
            "Name_")

        user_data = {
            "nombres": "Name",
            "apellidoPaterno": "Last",
            "apellidoMaterno": None}
        self.assertEqual(
            generate_username(user_data),
            "Name_Last")

    def test_whitespace_lastname(self):
        """
            Test generate username when lastname has too much whitespace
        """
        user_data = {
            "nombres": "Name",
            "apellidoPaterno": "          Last    Last2      ",
            "apellidoMaterno": '    Last2      '}
        self.assertEqual(
            generate_username(user_data),
            "Name_Last")

    def test_long_name_middle(self):
        """
            Test generate username when long name middle
        """
        data = {
            'username': 'test.name',
            'apellidoMaterno': 'ff',
            'nombres': 'a23456789012345678901234 bb',
            'apellidoPaterno': '4567890',
            'doc_id': '0112223334',
            'email': 'test@test.test'
        }
        self.assertEqual(create_user_by_data(
            data, 'test@test.test', False).username, 'a234567890123456789012341')

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
            'doc_ids': '10-8',
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

    def test_staff_post_multiple_doc_id(self):
        """
            Test staff view post with multiple 'run'
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8\n9045578-8\n7193711-9\n19961161-5\n24902414-7',
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

    def test_staff_post_multiple_doc_id_multiple_course(self):
        """
            Test staff view post with multiple 'run' and multiple courses
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8\n9045578-8\n7193711-9\n19961161-5\n24902414-7',
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
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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

    def test_staff_post_duplicate_multiple_doc_ids(self):
        """
            Test staff view post when doc_ids is duplicated in form
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8\n10-8\n10-8\n10-8\n10-8',
            'course': 'course-v1:tet+MSS001+2009_2',
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"duplicate_doc_ids\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_multiple_course_no_permission(self):
        """
            Test staff view post multiple course when user dont have permission
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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

    def test_staff_post_sin_doc_id(self):
        """
            Test staff view post when 'doc_ids' is empty
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"no_doc_id\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_doc_id_malo(self):
        """
            Test staff view post when 'doc_ids' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '12345678-9',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_exits_user_enroll(self):
        """
            Test staff view post with auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '9472337-k',
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
        self.assertTrue("id=\"doc_id_saved_enroll\"" in response._container[0].decode())

    def test_staff_post_exits_user_no_enroll(self):
        """
            Test staff view post without auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '9472337-k',
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
            "id=\"doc_id_saved_enroll_no_auto\"" in response._container[0].decode())

    @patch('requests.get')
    def test_staff_post_force_enroll(self, get):
        """
            Test staff view post with force enroll normal process
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_enroll\"" not in response._container[0].decode())
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
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_enroll\"" not in response._container[0].decode())
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
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_enroll\"" not in response._container[0].decode())
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
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_enroll\"" not in response._container[0].decode())
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
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_enroll\"" not in response._container[0].decode())
        edxlogin_user = EdxLoginUser.objects.get(run="0000000108")
        self.assertEqual(edxlogin_user.run, "0000000108")
        self.assertTrue(edxlogin_user.user.email in ['student22@edx2.org', 'student55@edx.org'])

    @patch('requests.get')
    def test_staff_post_force_enroll_email_diff_doc_id(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_2(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_3(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_4(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_enroll_error_to_get_data_5(self, get):
        """
            Test staff view post with force enroll when fail to get data from ph api
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force\"" not in response._container[0].decode())
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())
        self.assertEqual(EdxLoginUserCourseRegistration.objects.count(), 1)
        self.assertFalse(EdxLoginUser.objects.filter(run="0000000108").exists())

    @patch('requests.get')
    def test_staff_post_force_no_enroll(self, get):
        """
            Test staff view post with force enroll without auto enroll
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_force_no_auto\"" in response._container[0].decode())
        self.assertTrue(
            "id=\"doc_id_saved_enroll_no_auto\"" not in response._container[0].decode())
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
            'doc_ids': '10-8',
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
        self.assertTrue("id=\"doc_id_saved_pending\"" in response._container[0].decode())

    def test_staff_post_no_action_params(self):
        """
            Test staff view post without action
        """
        post_data = {
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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
        self.assertEqual(r['doc_id_saved']['doc_id_saved_force'], "TEST_TESTLASTNAME - 0000000108")        
        self.assertEqual(aux.user.email, "test@test.test")

    @patch('requests.get')
    def test_staff_post_instructor_staff(self, get):
        """
            Test staff view post when user have permission
        """
        post_data = {
            'action': "enroll",
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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
        self.assertEqual(r['doc_id_saved']['doc_id_saved_force'], "TEST_TESTLASTNAME - 0000000108")

    @patch('requests.get')
    def test_staff_post_instructor_multiple_course(self, get):
        """
            Test staff view post when user is instructor and multiple course
        """
        post_data = {
            'action': "enroll",
            'doc_ids': '10-8',
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
        self.assertEqual(r['doc_id_saved']['doc_id_saved_force'], "TEST_TESTLASTNAME - 0000000108")

    def test_staff_post_unenroll_no_db(self):
        """
            Test staff view post unenroll when user no exists
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['doc_id_unenroll_no_exists'], ['0000000108'])

    def test_staff_post_unenroll_edxlogincourse(self):
        """
            Test staff view post unenroll when user have edxlogincourse 
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
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
        self.assertEqual(r['doc_id_unenroll'], ['0000000108'])
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_unenroll_enrollment(self):
        """
            Test staff view post unenroll when user have enrollment 
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
            'course': self.course.id,
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['doc_id_unenroll'], ['0000000108'])

    def test_staff_post_unenroll_enrollment_multiple_course(self):
        """
            Test staff view post unenroll when user have enrollment 
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
            'course': '{}\n{}'.format(str(self.course.id), str(self.course2.id)),
            'modes': 'audit',
        }
        EdxLoginUser.objects.create(user=self.student, run='0000000108')
        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        r = json.loads(response._container[0].decode())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['doc_id_unenroll'], ['0000000108'])

    def test_staff_post_unenroll_allowed(self):
        """
            Test staff view post unenroll when user have CourseEnrollmentAllowed 
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
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
        self.assertEqual(r['doc_id_unenroll'], ['0000000108'])

    def test_staff_post_unenroll_student(self):
        """
            Test staff view post unenroll when user is student 
        """
        post_data = {
            'action': "unenroll",
            'doc_ids': '10-8',
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
            'doc_ids': '10-8',
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
            'doc_ids': 'P12345',
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
            'doc_ids': 'CG12345678',
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
            Test staff view post when 'doc_ids' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': 'P213',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())
        self.assertEqual(
            EdxLoginUserCourseRegistration.objects.all().count(), 0)

    def test_staff_post_wrong_CG(self):
        """
            Test staff view post when 'doc_ids' is wrong
        """
        post_data = {
            'action': "staff_enroll",
            'doc_ids': 'CG128',
            'course': self.course.id,
            'modes': 'audit',
            'enroll': '1'
        }

        response = self.client.post(
            reverse('uchileedxlogin-login:staff'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())
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

    def test_external_post_without_doc_id(self):
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

    def test_external_post_without_doc_id_multiple_course(self):
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

    def test_external_post_without_doc_id_exists_email(self):
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

    def test_external_post_without_doc_id_exists_email_multiple_course(self):
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
    def test_external_post_with_doc_id(self, get):
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
    def test_external_post_with_doc_id_exists_email(self, get):
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

    def test_external_post_with_exists_doc_id(self):
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

    def test_external_post_without_doc_id_multiple_data(self):
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

    def test_external_post_wrong_doc_id(self):
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

    def test_external_post_duplicate_multiple_doc_id(self):
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
        self.assertTrue('id="duplicate_doc_id"' in response._container[0].decode())

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

    def test_external_post_without_doc_id_name_with_special_character_2(self):
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

    def test_external_post_without_doc_id_name_with_special_character(self):
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
    def test_external_post_with_doc_id_email_diff_doc_id(self, get):
        """
            Test external view post with doc_id, when email already have another doc_id params
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
    def test_external_post_with_doc_id_fail_get_data(self, get):
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
    def test_external_post_with_doc_id_fail_get_data_2(self, get):
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
    def test_external_post_with_doc_id_fail_get_data_3(self, get):
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
    def test_external_post_with_doc_id_fail_get_data_4(self, get):
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
    def test_external_post_with_doc_id_fail_get_data_5(self, get):
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


class TestInterfaceUtils(ModuleStoreTestCase):    
    def test_validate_rut_valid_rut(self):
        """
            Test validate_rut for some valid ruts
        """
        is_valid_rut = validate_rut("17.502.502-K")
        self.assertFalse(is_valid_rut)

        is_valid_rut = validate_rut("17.502.5022")
        self.assertTrue(is_valid_rut)

        is_valid_rut_2 = validate_rut("18.125.751-2")
        self.assertTrue(is_valid_rut_2)

        is_valid_rut_3 = validate_rut("18125713-K")
        self.assertTrue(is_valid_rut_3)


    def test_validate_rut_invalid_rut(self):
        """
            Test validate_rut for some invalid ruts
        """
        is_valid_rut = validate_rut("17.502.502-K")
        self.assertFalse(is_valid_rut)

        is_valid_rut_2 = validate_rut("18.125.751-7")
        self.assertFalse(is_valid_rut_2)

        is_valid_rut_3 = validate_rut("18125713-5")
        self.assertFalse(is_valid_rut_3)

    def test_get_document_type_passport(self):
        """
            Test get_document_type for passport document_id
        """
        self.assertEqual(get_document_type('P1234567'), 'passport')
        self.assertEqual(get_document_type('P1234567-K'), 'passport')

    def test_get_document_type_cg(self):
        """
            Test get_document_type for cg document_id
        """
        self.assertEqual(get_document_type('CG1234567'), 'cg')
        self.assertEqual(get_document_type('CG512331231'), 'cg')

    def test_get_document_type_rut(self):
        """
            Test get_document_type for rut document_id
        """
        self.assertEqual(get_document_type('17.502.502-K'), 'rut')
        self.assertEqual(get_document_type('18.125.751-2'), 'rut')
        self.assertEqual(get_document_type('234567'), 'rut')


class TestUtils(ModuleStoreTestCase):
    def setUp(self):
        super(TestUtils, self).setUp()
        self.user = UserFactory(
                username='testuser1',
                password='12345',
                email='test@test.com')
        self.user2 = UserFactory(
                username='testuser2',
                password='12345',
                email='test2@uchile.cl',
                is_staff=True)

    def test_select_email_empty(self):
        """
            Test select_email for an empty email list
        """
        self.assertEqual(select_email([]),'')

    def test_select_email_unused_email(self):
        """
            Test select_email for an email list with one used and one unused email
        """
        self.assertEqual(select_email(['test@test.com', 'unused_mail@test.com']), 'unused_mail@test.com')

    def test_select_email_all_emails_used(self):
        """
            Test select_email for a list with all emails already in use
        """
        self.assertEqual(select_email(['test@test.com', 'test2@uchile.cl']), '')

    def test_select_email_unused_uchile_email(self):
        """
            Test select_email for a list with unused mails, including a @uchile.cl one
        """
        self.assertEqual(select_email(['unused_test@test.com', 'unused@uchile.cl']), 'unused@uchile.cl')

    def test_get_user_from_emails(self):
        """
            Test get_user_from_emails for an empty email list
        """
        self.assertEqual(get_user_from_emails(['test@test.com']), self.user)

    def test_get_user_from_emails_uchile(self):
        """
            Test get_user_from_emails for an email list including a @uchile.cl one
        """
        self.assertEqual(get_user_from_emails(['test@test.com', 'test2@uchile.cl']), self.user2)

    def test_get_user_from_emails_linked_mails(self):
        """
            Test get_user_from_emails when all emails in the list are already linked
        """
        create_edxloginuser(self.user, False, '009472337K')
        create_edxloginuser(self.user2, False, '0094723373')
        self.assertEqual(get_user_from_emails(['test@test.com', 'test2@uchile.cl']), None)

    def test_validate_all_doc_id_types_valid_passport(self,):
        """
            Test validate_all_id_types for valid passports
        """
        self.assertTrue(validate_all_doc_id_types('P1234567'))
        # Min passport length
        self.assertTrue(validate_all_doc_id_types('P12345' ))
        # Max passport length
        self.assertTrue(validate_all_doc_id_types('P' + '1' * 20))

    def test_validate_all_doc_id_types_invalid_passport(self):
        """
            Test validate_all_id_types for invalid passports
        """
        self.assertFalse(validate_all_doc_id_types('P1234'))
        self.assertFalse(validate_all_doc_id_types('P' + '1' * 21))

    def test_validate_all_doc_id_types_valid_cg(self):
        """
            Test validate_all_id_types for valid cg
        """
        self.assertTrue(validate_all_doc_id_types('CG12345678'))

    def test_validate_all_doc_id_types_invalid_cg(self):
        """
            Test validate_all_id_types for invalid cg
        """
        self.assertFalse(validate_all_doc_id_types('CG1234567'))
        self.assertFalse(validate_all_doc_id_types('CG123456789'))

    @patch('uchileedxlogin.utils.validate_rut')
    def test_validate_all_doc_id_types_valid_rut(self, mock_validate_rut):
        """
            Test validate_all_id_types for valid rut
        """
        mock_validate_rut.return_value = True
        self.assertTrue(validate_all_doc_id_types('12.345.678-9'))

    @patch('uchileedxlogin.utils.validate_rut')
    def test_validate_all_doc_id_types_invalid_rut(self, mock_validate_rut):
        """
            Test validate_all_id_types for invalid rut
        """
        mock_validate_rut.return_value = False
        self.assertFalse(validate_all_doc_id_types('12.345.678-0'))

    def test_validate_all_doc_id_types_invalid_input(self):
        """
            Test validate_all_id_types for invalid input
        """
        self.assertFalse(validate_all_doc_id_types(11111))
        self.assertFalse(validate_all_doc_id_types(''))


class TestUserData(TestCase):
    def setUp(self):
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.client = Client()
            user = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.client.login(username='testuser3', password='12345')
            
            # user with permission
            self.client_user = Client()
            user_wper = UserFactory(
                username='testuser4',
                password='12345',
                email='student4@edx.org')
            self.client_user.login(username='testuser4', password='12345')

            # user without permission
            self.client_no_per = Client()
            user_nper = UserFactory(
                username='testuser5',
                password='12345',
                email='student5@edx.org')
            self.client_no_per.login(username='testuser5', password='12345')

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_get(self, mock_permission_check):
        mock_permission_check.return_value = True
        response = self.client.get(reverse('uchileedxlogin-login:data'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/edxuserdata/data/')

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_get_user_anonymous(self, mock_permission_check):
        """
            Test if the user is anonymous
        """
        mock_permission_check.return_value = False
        self.client_anonymous = Client()
        response = self.client_anonymous.get(reverse('uchileedxlogin-login:data'))
        request = response.request
        self.assertEqual(response.status_code, 404)
        self.assertEqual(request['PATH_INFO'], '/edxuserdata/data/')
    
    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_get_user_without_permission(self, mock_permission_check):
        """
            Test if the user does not have permission
        """
        mock_permission_check.return_value = False
        response = self.client_no_per.get(reverse('uchileedxlogin-login:data'))
        request = response.request
        self.assertEqual(response.status_code, 404)
        self.assertEqual(request['PATH_INFO'], '/edxuserdata/data/')

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_get_user_with_permission(self, mock_permission_check):       
        """
            Test if the user have permission
        """ 
        mock_permission_check.return_value = True
        response = self.client_user.get(reverse('uchileedxlogin-login:data'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/edxuserdata/data/')

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    @patch('requests.get')
    def test_staff_post(self, get, mock_permission_check):
        """
            Test normal process
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': '10-8'
        }
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME",
                                                            "materno": "TESTLASTNAME",
                                                            'pasaporte': [{'usuario':'avilio.perez'}],
                                                            "nombres": "TEST NAME",
                                                            'email': [{'email': 'test@test.test'}],
                                                            "indiv_id": "0000000108"}]}}})]
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        data = response.content.decode().split("\r\n")
        self.assertEqual(data[0], "Documento_id;Username;Apellido Paterno;Apellido Materno;Nombre;Email")
        self.assertEqual(
            data[1],
            "0000000108;avilio.perez;TESTLASTNAME;TESTLASTNAME;TEST NAME;test@test.test")

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    @patch('requests.get')
    def test_staff_post_fail_data(self, get, mock_permission_check):
        """
            Test if get data fail
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': '10-8'
        }
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "json"])(400,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME",
                                                            "materno": "TESTLASTNAME",
                                                            'pasaporte': [{'usuario':'avilio.perez'}],
                                                            "nombres": "TEST NAME",
                                                            'email': [{'email': 'test@test.test'}],
                                                            "indiv_id": "0000000108"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        data = response.content.decode().split("\r\n")
        self.assertEqual(data[0], "Documento_id;Username;Apellido Paterno;Apellido Materno;Nombre;Email")
        self.assertEqual(
            data[1],
            "0000000108;No Encontrado;No Encontrado;No Encontrado;No Encontrado;No Encontrado")

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    @patch('requests.get')
    def test_staff_post_multiple_doc_id(self, get, mock_permission_check):
        """
            Test normal process with multiple 'r.u.n'
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': '10-8\n9472337K'
        }
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                               lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME",
                                                            "materno": "TESTLASTNAME",
                                                            'pasaporte': [{'usuario':'avilio.perez'}],
                                                            "nombres": "TEST NAME",
                                                            'email': [{'email': 'test@test.test'}],
                                                            "indiv_id": "0000000108"}]}}}),
                    namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                               lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME2",
                                                            "materno": "TESTLASTNAME2",
                                                            'pasaporte': [{'usuario':'test.test'}],
                                                            "nombres": "TEST2 NAME2",
                                                            'email': [{'email': 'test2@test.test'}],
                                                            "indiv_id": "009472337K"}]}}})]

        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        data = response.content.decode().split("\r\n")

        self.assertEqual(data[0], "Documento_id;Username;Apellido Paterno;Apellido Materno;Nombre;Email")
        self.assertEqual(
            data[1],
            "0000000108;avilio.perez;TESTLASTNAME;TESTLASTNAME;TEST NAME;test@test.test")
        self.assertEqual(
            data[2],
            "009472337K;test.test;TESTLASTNAME2;TESTLASTNAME2;TEST2 NAME2;test2@test.test")

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_post_no_doc_id(self, mock_permission_check):
        """
            Test post if doc_ids is empty
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': ''
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        self.assertTrue("id=\"no_doc_id\"" in response._container[0].decode())

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_post_wrong_doc_id(self, mock_permission_check):
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': '123456'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_post_wrong_passport(self, mock_permission_check):
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': 'P3456'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    def test_staff_post_wrong_CG(self, mock_permission_check):
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': 'CG123456'
        }
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        self.assertTrue("id=\"invalid_doc_ids\"" in response._container[0].decode())

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    @patch('requests.get')
    def test_staff_post_passport(self, get, mock_permission_check):
        """
            Test normal process with passport
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': 'p123456'
        }
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME",
                                                            "materno": "TESTLASTNAME",
                                                            'pasaporte': [{'usuario':'avilio.perez'}],
                                                            "nombres": "TEST NAME",
                                                            'email': [{'email': 'test@test.test'}],
                                                            "indiv_id": "P123456"}]}}})]
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        data = response.content.decode().split("\r\n")
        self.assertEqual(data[0], "Documento_id;Username;Apellido Paterno;Apellido Materno;Nombre;Email")
        self.assertEqual(
            data[1],
            "P123456;avilio.perez;TESTLASTNAME;TESTLASTNAME;TEST NAME;test@test.test")

    @patch('uchileedxlogin.views.check_permission_instructor_staff')
    @patch('requests.get')
    def test_staff_post_CG(self, get, mock_permission_check):
        """
            Test normal process with CG
        """
        mock_permission_check.return_value = True
        post_data = {
            'doc_ids': 'CG00123456'
        }
        get.side_effect = [namedtuple("Request",
                                      ["status_code",
                                       "json"])(200,
                                                lambda:{'data':{'getRowsPersona':{'status_code':200,'persona':[
                                                            {"paterno": "TESTLASTNAME",
                                                            "materno": "TESTLASTNAME",
                                                            'pasaporte': [{'usuario':'avilio.perez'}],
                                                            "nombres": "TEST NAME",
                                                            'email': [{'email': 'test@test.test'}],
                                                            "indiv_id": "CG00123456"}]}}})]
        response = self.client.post(
            reverse('uchileedxlogin-login:data'), post_data)
        data = response.content.decode().split("\r\n")
        self.assertEqual(data[0], "Documento_id;Username;Apellido Paterno;Apellido Materno;Nombre;Email")
        self.assertEqual(
            data[1],
            "CG00123456;avilio.perez;TESTLASTNAME;TESTLASTNAME;TEST NAME;test@test.test")
