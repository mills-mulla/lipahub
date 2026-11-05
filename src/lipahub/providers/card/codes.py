from ...core.types import FailureCode as F
from ...core.types import Outcome as O


STATUS_CODES = {
    "success": (O.SUCCEEDED, ""),
    "failed": (O.FAILED, F.PROVIDER_ERROR),
    "reversed": (O.FAILED, F.PROVIDER_ERROR),
    "abandoned": (O.PENDING, ""),
    "ongoing": (O.PENDING, ""),
    "pending": (O.PENDING, ""),
    "processing": (O.PENDING, ""),
    "queued": (O.PENDING, ""),

}

def map_status(s):
    return STATUS_CODES.get(str(s).lower(), (O.PENDING, ""))