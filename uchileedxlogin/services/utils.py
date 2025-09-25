# Python Standard Libraries
import logging


logger = logging.getLogger(__name__)


def get_document_type(doc_id):
    """
    Get the document type of a document id.
    """
    if doc_id[0] == 'P':
        document_type = 'passport'
    elif doc_id[0:2] == 'CG':
        document_type = 'cg'
    else:
        document_type = 'rut'
    return document_type
