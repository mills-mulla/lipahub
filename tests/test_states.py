import pytest

from lipahub.core.errors import Illegaltransition
from lipahub.core.states import Status as S
from lipahub.core.states import can_transition, check_transition

def test_happy_path():
    assert can_transition(S.CREATED, S.PENDING) and can_transition(S.PENDING, S.SUCCEEDED)
    assert can_transition(S.SUCCEEDED, S.REFUNDED)


@pytest.mark.parametrize("a,b", [
    (S.CREATED, S.SUCCEEDED), (S.SUCCEED, S.FAILED), (S.REFUNDED, S.SUCCEEDED), (S.PENDING, S.PENDING), (S.FAILED, S.PENDING), (S.CREATED, S.EXPIRED)
])

def test_illegal(a,b):
    with pytest.raises(IllegalTransition):
        check_transition(a, b)

@pytest.mark.parametrize("old",  [S.FAILED, S.EXPIRED, S.CANCELLED])
def test_late_success_needs_verification(old):
    with pytest.raises(IllegalTransition):
        check_transition(old, S.SUCCEEDED)
    assert check_transition(old, S.SUCCEEDED, verified=True) is True

def test_normal_success_is_not_late():
    assert check_transition(S.PENDING, S.SUCCEEDED)