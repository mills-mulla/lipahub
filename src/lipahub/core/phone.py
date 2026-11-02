import re

from .error import InvalidPhoneNumber

def normalize_msisdn(raw, default_country="254") -> str:
    s = re.sub(r"[\s\-()]", "", str(raw or ""))
    if s.startswith("+"):
        digits = s[1:]
    elif s.startswith("00"):
        digits = s[2:]
    elif s.startswith("0"):
        digits = default_country + s[1:]
    elif default_country == "254" and len(s) == 9 and s[0] in "17":
        digits = default_country + s
    else:
        digits =s
    
    if not digits.isdigit() or not 10 <= len(digits) <= 15:
        raise InvalidPhoneNumber("invalid phone number")

    return "+" + digits

def mask_msisdn(value) -> str:
    v = str(value or "")
    return v if len(v) < 9 else v[:5] + "*" * (len(v) - 8) + v[-3:]