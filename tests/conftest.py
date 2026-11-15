import pytest

@pytest.fixture
def fake():
    from src.lipahub import registry
    from src.lipahub.providers.fake import FakeAdapter

    registry.reset()
    adapter = FakeAdapter({"callback_token": "tok"})
    registry.register("fake", adapter)
    yield adapter
    registry.reset()
    