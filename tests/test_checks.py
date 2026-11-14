from django.test import override_settings
from src.lipahub.checks import lipahub_checks


def ids():
    return {w.id for w in lipahub_checks(None)}

def test_missing_token_warns():
    with override_settings(LIPAHUB={"CALLBACK_TOKEN": ""}):
        assert "lipahub.W004" in ids()

def test_token_set_no_warning():
    with override_settings(LIPAHUB={"CALLBACK_TOKEN": "x"}):
        assert "lipahub.W004" not in ids()
    
def test_sqlite_warns():
    assert "lipahub.W001" in ids() 

def test_atommic_requests_warn():
    dbs = {"default": {"ENGINE": "django.db.backends.postgresql", "ATOMIC_REQUESTS": True}}
    with override_settings(DATABASES=dbs):
        assert "lipahub.W002" in ids()
 


