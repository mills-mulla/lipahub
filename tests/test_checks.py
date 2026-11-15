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
 
def test_typo_in_setting_is_an_error():
    with override_settings(LIPAHUB={"CALLBACK_TOKEM": "x"}):
        assert "lipahub.E001" in ids()
def test_bad_task_runner_is_an_error():
    with override_settings(LIPAHUB={"TASK_RUNNER": "x"}):
        assert "lipahub.E002" in ids()
def test_provider_without_adapter_is_an_error():
    with override_settings(LIPAHUB={"PROVIDERS": {"foo": {}}}):
        assert "lipahub.E003" in ids()

def test_valid_settings_have_no_errors():
    from src.lipahub.settings import validate
    assert [p for p in validate() if p[0] == "error"] == []


