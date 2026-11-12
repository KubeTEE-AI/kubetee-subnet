"""Adversarial transport construction: no network or secret disclosure."""
import pytest

from worker.config import redis_production_settings

def test_sentinel_uri_discovers_master_and_decodes_credentials():
    from redis.asyncio import Redis
    from redis.asyncio import Sentinel
    parsed = redis_production_settings(
        "redis+sentinel://litellm:p%40ss%2Fword@litellm-redis:26379?service_name=mymaster"
    )
    nodes = parsed.pop("sentinel_nodes")
    name = parsed.pop("service_name")
    auth = parsed.pop("sentinel_kwargs")
    client = Sentinel(nodes, sentinel_kwargs=auth).master_for(name, **parsed)
    pool = client.connection_pool
    from redis.asyncio.sentinel import SentinelConnectionPool
    assert isinstance(pool, SentinelConnectionPool)
    assert pool.service_name == "mymaster"
    assert pool.master_address is None
    assert pool.connection_kwargs["username"] == "litellm"
    assert pool.connection_kwargs["password"] == "p@ss/word"
    assert pool.connection_kwargs["decode_responses"] is True
    assert pool.connection_kwargs["socket_connect_timeout"] == 5.0

def test_direct_redis_password_and_db_stay_in_their_fields():
    from redis.asyncio import Redis
    client = Redis(**redis_production_settings("redis://:p%40ss%2Fword@litellm-redis:6379/2"))
    assert client.connection_pool.connection_kwargs["password"] == "p@ss/word"
    assert client.connection_pool.connection_kwargs["db"] == 2

@pytest.mark.parametrize("url", [
    "redis+sentinel://u:pw@host:26379",
    "redis+sentinel://u:pw@host:26379?service_name=../../secret",
    "redis+sentinel://u:pw@host:26379?service_name=mymaster&password=override",
    "redis+sentinel://u:pw@host:26379?service_name=mymaster&service_name=other",
    "rediss://u:pw@host:6379/evil",
    "http://u:pw@host:6379?service_name=mymaster",
])
def test_invalid_or_ambiguous_transport_config_fails_without_leaking_secret(url):
    with pytest.raises(ValueError, match="invalid production Redis URI configuration") as error:
        redis_production_settings(url)
    assert "pw" not in str(error.value)
