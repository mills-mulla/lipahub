from decimal import Decimal

import pytest

from  lipahub.core.errors import InvalidAmount, InvalidPhoneNumber
from  lipahub.core.money import to_major, to_minor, validate_minor, whone_units
from  lipahub.core.phone import mask_msisdn, normalize_msisdn
from  lipahub.core.redact import scrub

def test_to_minor():
    assert to_minor(15) == 1500 and to_minor("15.50") == 1550 and to_minor(Decimal("0.01")) == 1
    assert to_minor(100, "UGX") == 100

@pytest.mark.parametrize("bad", ["15.555", "abc", True, 0, -5])
def test_to_minor_rejects(bad):
    with pytest.raises(InvalidAmount):
        to_minor(bad)
    
def test_never_truncates():
    with pytest.raises(InvalidAmount):
        to_minor(10.005)

def test_whole_units():
    assert whole_units(15000, "KES") == 150
    with pytest.raises(InvalidAmount):
        whole_units(15050, "KES")
    
def test_validate_minor():
    assert validate_minor(5) == 5
    for bad in (0, -1, 1.5, "5", True):
        with pytest.raises(InvalidAmount):
            validate_minor(bad)

def test_to_major():
    assert to_major(1550) == Decimal("15.50")


@pytest.mark.parametrize("raw", ["0700123456", "700123456", "+254700123456", "254700123456", "0700 123 456", "00254700123456"])
def test_normalize_msisdn(raw):
    assert normalize_msisdn(raw) == "+254700123456"

def test_bad_phone():
    with pytest.raises(InvalidPhoneNumber):
        normalize_msisdn("123ab")

def test_mask_and_scrub():
    assert mask_msisdn("+254700123456") == "+2547*****456"
    out = scrub({"MSISDN": "25400123456", "Item":[{"Name": "PhoneNumber", "Value": 254700123456}, {"Name": "Amount", "Value", 1}]})
    assert "700123" not in str(out) and out["Item"][1]["Value"] == 1


