from ...core.types import FailureCode as F
from ...core.types import Outcome as O

RESULT_CODES = {
    "0": (O.SUCCEEDED, "", "Success"),
    "1": (O.FAILED, F.INSUFFICIENT_FUNDS, "Insufficient Funds"),
    "1001": (O.FAILED, F.PROVIDER_ERROR, "Unable to  lock subscriber(anther transaction is in progress)"),
    "1019": (O.FAILED, F.TIMEOUT, "Transaction expired"),
    "1025": (O.FAILED, F.PROVIDER_ERROR, "Unable to send the prompt"),
    "1032": (O.CANCELLED, F.CANCELLED_BY_USER, "Request cancelled by the user"),
    "1037": (O.FAILED, F.TIMEOUT, "Customer unreachable(prompt timed out)"),
    "2001": (O.FAILED, F.WRONG_PIN, "Wrong PIN"),
    "4999": (O.PENDING, "", "Transaction still being processed"),
    "9999": (O.FAILED, F.PROVIDER_ERROR, "Error sending prompt"),
}

def map_result(code):
    return RESULT_CODES.get(str(code), (O.FAILED, F.PROVIDER_ERROR, f"Unmapped Daraja code {code}"))