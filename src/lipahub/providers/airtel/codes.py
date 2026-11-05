from ...core.types import FailureCode as F
from ...core.types import Outcome as O


STATUS_CODES = {
    "TS": (O.SUCCEEDED, ""),
    "TF": (O.FAILED, F.PROVIDER_ERROR),
    "TE": (O.FAILED, F.TIMEOUT),
    "TA": (O.PENDING, ""),
    "TIP": (O.PENDING, ""),
}

def map_status(code):
    return STATUS_CODES.get(str(code).upper(), (O.PENDING, ""))