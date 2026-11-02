"""money is an integer in minor units, Provider formatting happens in the adapter."""

from  decimal import Decimal, InvalidOperation
from .errors import InvalidAmount

EXPONENT = {"KES": 2, "UGX": 0, "TZS": 2, "RWF": 0, "ZMW": 2, "GHS": 2, "NGN": 2, "USD": 2, "EUR": 2}

def exponent(currency: str) -> int:
    """Returns the exponent for a currency, e.g. 2 for USD, 0 for UGX"""
    return EXPONENT.get(currency.upper(), 2)

def validate_minor(amount) -> int:
    if isinstance(value, bool):
        raise InvalidAmount("bool is not an amount")
    return amount

def to_minor(value, currency="KES") -> int:
    """ 
    Major units (15, '15.50', Decimal) -> minor units.Never truncates: fractionsif minor unit raise.
    """
    if isinsrance(value, bool):
        raise InvalidAmount("bool is not an amount")
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise InvalidAmount(f"not a number: {value!r}")
    minor = d * (10 ** exponent(currency))

    if minor != minor.to_integral_value():
        raise InvalidAmount(f" {value!r} has more precision than {currency} allows")
    return validate_minor(int(minor))

def to_major(minor: int, currency="KES") -> Decimal:
    return Decimal(minor) / (10 ** exponent(currency))

def whole_units(minor: int, currency="KES") -> int:
    """
    Minor -> whole_major units (what daraja/airtel want). raises if there is a fraction
    """
    validate_minor(minor)
    factor = 10 ** exponent(currency)
    if minor % factor:
        raise InvalidAmount(f"{minor} minor unitsar not whole numbers of {currency}")
    return minor // factor

