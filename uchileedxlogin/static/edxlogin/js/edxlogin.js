function limitTextarea(textarea, maxLines) {      
  var lines = textarea.value.replace(/\r/g, '').trim();
  lines = lines.split('\n');
  lines = lines.filter(function(el) { return el; });              
  if (maxLines && lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      textarea.value = lines.join('\n')
  }
}
function enrollrun(e){      
  var runs = document.getElementById("student-run");//value
  var csrf = document.getElementById("csrf");//value
  var role = document.getElementById("role-run"); //value
  var course_id = document.getElementById("course_id"); //value
  var auto = true; //auto-enroll
  
  if (!runs.value) {
      fail_with_error('El campo de Rut no pude dejarse vacío.');
      return false;
  }
  if (!role.value) {
      fail_with_error('El campo de Rol no pude dejarse vacío.');
      return false;
  }
  var sendData = {
      csrfmiddlewaretoken: csrf.value,
      action: e.dataset.action,
      runs: runs.value,
      modes: role.value,
      course: course_id.value,
      enroll: auto,
      force: true
  };
  return $.ajax({
      dataType: 'json',
      type: 'POST',
      url: e.dataset.endpoint,
      data: sendData,
      success: function(data) {
          return display_response(data);
      },
      error: statusAjaxError(function() {
          return fail_with_error("Error inesperado ha ocurrido. Actualice la página e intente nuevamente");
      })
  });        
}
clear_input = function() {
  var runs = document.getElementById("student-run");//value
  var role = document.getElementById("role-run"); //value

  runs.value='';
  role.value="honor"
};

fail_with_error = function(msg) {
  var task_response = document.getElementById("enroll-run-response");
  var request_response_error = document.getElementById("enroll-run-response-error");

  clear_input();
  task_response.textContent = "";
  request_response_error.textContent = msg;        
};
validate_error = function(data) {
  var aux_error = "";
  if ("run_malos" in data){          
    aux_error = aux_error + "Estos Ruts están incorrectos: " + data.run_malos + "</br>";
  }
  if ("no_run" in data){
    aux_error = aux_error + "Falta agregar rut.</br>";
  }
  if ("curso2" in data){
    aux_error = aux_error + "No se ha ingresado el id del curso, actualice la página e intentelo nuevamente</br>";
  }
  if ("error_curso" in data){
    aux_error = aux_error + "Los siguientes ids de curso no exiten, actualice la página e intentelo nuevamente:</br>";
    data.error_curso.forEach(course_id => {
      aux_error = aux_error + course_id + "</br>";
    });
  }
  if ("error_permission" in data){
    aux_error = aux_error + "Usuario no tiene permiso suficientes en los siguientes cursos:</br>";
    data.error_permission.forEach(course_id => {
      aux_error = aux_error + course_id + "</br>";
    });
  }
  if ("duplicate_ruts" in data){
    aux_error = aux_error + "Estos ruts están duplicados en el formulario:</br>";
    data.duplicate_ruts.forEach(rut => {
      aux_error = aux_error + rut + "</br>";
    });
  }
  if ("duplicate_courses" in data){
    aux_error = aux_error + "Estos cursos están duplicados en el formulario:</br>";
    data.duplicate_courses.forEach(course_id => {
      aux_error = aux_error + course_id + "</br>";
    });
  }
  if ("error_mode" in data){
    aux_error = aux_error + "El rol del usuario esta incorrecto, actualice la página</br>";
  }
  if ("error_action" in data){
    aux_error = aux_error + "La acción que quiere realizar es incorrecta, actualice la página</br>";
  }
  if (aux_error != ""){
    aux_error = "<b>No se ha inscrito/desinscrito ningún rut por los siguentes motivos: </b></br>" + aux_error;
    aux_error = aux_error + "<span style='color:darkorange'><b>Las cuentas pasaportes deben tener una 'P' al inicio y debe tener entre 5 y 20 caracteres</b></span></br>";
  }        
  return aux_error
};
validate_success = function(data) {
  var aux_success = "";
  
  if ("saved" in data && data.saved == "saved"){          
    if (data.run_saved['run_saved_pending'] != ""){
      aux_success = aux_success + "No se ha encontrado ninguna cuenta institucional de los siguientes ruts: " + data.run_saved['run_saved_pending'] + "</br>";
      aux_success = aux_success + "Al momento de registrarse, automaticamente se inscribirán en el curso.</br></br>";
    }
    if (data.run_saved['run_saved_enroll'] != "" || data.run_saved['run_saved_force'] != ""){
      var run_saved_enroll = data.run_saved['run_saved_enroll'].split("/")
      var run_saved_force = data.run_saved['run_saved_force'].split("/")

      aux_success = aux_success + "<b>Usuarios inscritos correctamente: </b></br>";
      run_saved_enroll.forEach(run => {
        aux_success = aux_success + run + "</br>";
      });
      run_saved_force.forEach(run => {
        aux_success = aux_success + run + "</br>";
      });
    }
    clear_input();
  }
  if ("saved" in data && data.saved == "unenroll"){
    if (data.run_unenroll.length > 0 ){
      aux_success = aux_success + "<b>Ruts desinscrito correctamente: </b></br>";
      data.run_unenroll.forEach(run => {
          aux_success = aux_success + run + "</br>";
      });
    }

    if (data.run_unenroll_no_exists.length > 0){
      aux_success = aux_success + "<b>Los siguientes ruts no estaban inscritos en el curso: </b></br>";
      data.run_unenroll_no_exists.forEach(run => {
        aux_success = aux_success + run + "</br>";
      });
    }
    clear_input();
  }
  return aux_success
};
display_response = function(data) {
  var task_response = document.getElementById("enroll-run-response");
  var request_response_error = document.getElementById("enroll-run-response-error");
  
  request_response_error.innerHTML = validate_error(data);
  task_response.innerHTML = validate_success(data);
  return true;
};  