import pytest
from unittest.mock import patch
from fakeredis import FakeStrictRedis


@pytest.fixture(autouse=True)
def redis():
    """ Patches the redis connection """
    fake_redis = FakeStrictRedis()
    with patch("autotester.cli.redis_connection", return_value=fake_redis):
        with patch(
            "autotester.server.utils.redis_management.redis_connection", return_value=fake_redis,
        ):
            yield fake_redis
