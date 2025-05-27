# Python Standard Libraries
import logging

# Installed packages (via pip)
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# Functions that make queries to ph.
def check_doc_id_have_sso(doc_id):
    """
    Check if the doc_id have sso.
    """
    headers = {
        'AppKey': settings.EDXLOGIN_KEY,
        'Origin': settings.LMS_ROOT_URL
    }
    params = (('indiv_id', doc_id),)
    base_url = settings.EDXLOGIN_USER_INFO_URL
    result = requests.get(base_url, headers=headers, params=params)
    if result.status_code != 200:
        logger.error(
            "{} {}".format(
                result.request,
                result.request.headers))
        return False
    data = result.json()
    if data["data"]["getRowsPersona"] is None:
        return False
    if data['data']['getRowsPersona']['status_code'] != 200:
        logger.error(
            "Api Error: {}, body: {}, doc_id: {}".format(
                data['data']['getRowsPersona']['status_code'],
                result.text,
                doc_id))
        return False
    if len(data["data"]["getRowsPersona"]["persona"]) == 0:
        return False
    if len(data["data"]["getRowsPersona"]["persona"][0]['pasaporte']) == 0:
        return False
    return True


def get_user_data(query_value, query_type):
    """
    Get the user data by query_value, depending on query_type.
    e.g.:
    For query_type: 'indiv_id' and value_type: 12345678, gets the data related to that user doc_id
    from the ph api.
    For query_type: 'usuario' and value_type: nombre_apellido, gets the data related to that user
    username from the ph api.
    """
    headers = {
        'AppKey': settings.EDXLOGIN_KEY,
        'Origin': settings.LMS_ROOT_URL
    }
    params = ((query_type, '"{}"'.format(query_value)),)
    base_url = settings.EDXLOGIN_USER_INFO_URL
    result = requests.get(base_url, headers=headers, params=params)

    if result.status_code != 200:
        logger.error(
            "API request failed, HTTP status: {}, body: {}, query_value: {}".format(
                result.status_code,
                result.text,
                query_value))
        raise Exception(
            "API request failed, HTTP status: {}, query_value: {}".format(
                result.status_code, query_value))

    data = result.json()
    if data["data"]["getRowsPersona"] is None:
        logger.error(
            "Missing 'getRowsPersona' in API response, status_code: {}, body: {}, query_value: {}".format(
                result.status_code,
                result.text,
                query_value))
        raise Exception(
            "Missing 'getRowsPersona' in API response, status_code: {}, query_value: {}".format(
                result.status_code, query_value))
    if data['data']['getRowsPersona']['status_code'] != 200:
        logger.error(
            "PH API returned error status {}, expected 200, body: {}, username: {}".format(
                data['data']['getRowsPersona']['status_code'],
                result.text,
                query_value))
        raise Exception(
            "PH API returned error status {}, expected 200, query_value: {}".format(
                result.status_code, query_value))
    if len(data["data"]["getRowsPersona"]["persona"]) == 0:
        logger.error(
            "Empty persona list for query_value: {}, body: {}".format(
                query_value,
                result.text))
        raise Exception(
            "Empty persona list for query_value: {}, body: {}".format(
                query_value, result.text))
    if len(data["data"]["getRowsPersona"]["persona"][0]['pasaporte']) == 0:
        logger.error(
            "Empty pasaporte field for doc_id {}, body: {}".format(
                query_value,
                result.text))
        raise Exception(
            "Empty pasaporte field for doc_id {}, body: {}".format(
                query_value, result.text))
    getRowsPersona = data["data"]["getRowsPersona"]['persona'][0]
    user_data = {
        'doc_id': getRowsPersona['indiv_id'],
        'username': getRowsPersona['pasaporte'][0]['usuario'],
        'nombres': getRowsPersona['nombres'],
        'apellidoPaterno': getRowsPersona['paterno'],
        'apellidoMaterno': getRowsPersona['materno'],
        'emails': [email["email"] for email in getRowsPersona["email"]]
    }
    return user_data
