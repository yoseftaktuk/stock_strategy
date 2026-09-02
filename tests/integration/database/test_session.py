import pytest

from app.database.session import get_session_factory
from app.config.settings import Settings


@pytest.mark.integration
def test_session_factory_creates() -> None:
    settings = Settings()
    session_factory = get_session_factory(settings)
    session = session_factory()
    assert session is not None
    session.close()
