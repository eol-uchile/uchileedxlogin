# Python Standard Libraries
import logging
from itertools import cycle


logger = logging.getLogger(__name__)


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
