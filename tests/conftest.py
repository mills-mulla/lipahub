import pytest

@pytest.fixture
def fake():
    from lipahub import registry
    from lipahub.providers.fake import FakeAdapter

    registry.reset()
    adapter = FakeAdapter({"callback_token": "tok"})
    registry.register("fake", adapter)
    yield adapter
    registry.reset()
    