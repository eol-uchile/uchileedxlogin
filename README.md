# Uchile Edx Login

![Coverage Status](/coverage-badge.svg)

![https://github.com/eol-uchile/uchileedxlogin/actions](https://github.com/eol-uchile/uchileedxlogin/workflows/Python%20application/badge.svg) 

# Install App

    docker-compose exec lms pip install -e /openedx/requirements/uchileedxlogin
    docker-compose exec cms pip install -e /openedx/requirements/uchileedxlogin
    docker-compose exec lms python manage.py lms --settings=prod.production makemigrations
    docker-compose exec lms python manage.py lms --settings=prod.production migrate

# Install Theme

To enable enroll/unenroll users button in your theme add the next code:

- _../themes/your_theme/lms/templates/instructor/instructor_dashboard_2/membership.html_

    **add the script and css**

        <link rel="stylesheet" type="text/css" href="${static.url('edxlogin/css/edxlogin.css')}"/>
        <script type="text/javascript" src="${static.url('edxlogin/js/edxlogin.js')}"></script>

    **and add html button**

        % if request.user.has_perm('uchileedxlogin.uchile_instructor_staff') and (section_data['access']['instructor'] or section_data['access']['staff'] or section_data['access']['admin']):
            <fieldset class="batch-enrollment-run membership-run-section">
            <legend id="heading-batch-enrollment" class="hd hd-3">Inscripciones por Cuenta UChile</legend>
            <input type="hidden" id="csrf" name="csrfmiddlewaretoken" value="${csrf_token}"/>
            <input id="course_id" type="text" value="${sections[0]['course_id']}" hidden disabled>
            <label>
                Ingrese el RUT o Pasaporte de lo usuarios que desea inscribir. Si es más de uno, utilice saltos de lineas para diferenciar cada usuario.</br>
                Considere que los Pasaportes deben contener una 'P' al inicio (ejemplo: "PA123456")</br>
                <b>Máximo 50 rut.</b></br>
                <textarea rows="6" name="student-run" id="student-run" placeholder="12345678-k&#10;12345678-k" spellcheck="false" onkeyup="limitTextarea(this,50)"></textarea>
            </label>
            <div class="role">
                <label>
                    ${_("Role of the users being enrolled.")}
                    <select id="role-run" name="role-run">
                        <option value="honor" selected>Honor</option>
                        <option value="audit">Audit</option>
                    </select>
                </label>
            </div>
            <div>
                <input onclick="return enrollrun(this)" type="button" name="enrollment-run-button" class="enrollment-run-button" value="${pgettext('someone','Enroll')}" data-endpoint="${ reverse('uchileedxlogin-login:staff') }" data-action="enroll">
                <input onclick="return enrollrun(this)" type="button" name="enrollment-run-button" class="enrollment-run-button" value="${_("Unenroll")}" data-endpoint="${ reverse('uchileedxlogin-login:staff') }" data-action="unenroll">
            </div>
            <div id="enroll-run-response" class="request-response"></div>
            <div id="enroll-run-response-error" class="request-response-error"></div>
            </fieldset>
        %endif

## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run lms /openedx/requirements/uchileedxlogin/.github/test.sh
