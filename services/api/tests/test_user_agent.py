"""Every B2 request carries the sample's attribution user agent."""

from app.repo import b2_client

TOKEN = "b2ai-qdrant-multitenant-rag-tiering"


def test_s3_client_sets_custom_user_agent(monkeypatch):
    captured = {}

    def fake_client(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(b2_client.boto3, "client", fake_client)
    b2_client.get_s3_client.cache_clear()

    b2_client.get_s3_client()

    assert captured["args"] == ("s3",)
    assert captured["config"].user_agent_extra == TOKEN
    assert captured["endpoint_url"].startswith("https://s3.")
    assert captured["endpoint_url"].endswith(".backblazeb2.com")


def test_real_user_agent_string_contains_token(monkeypatch):
    # A syntactically valid placeholder; constructing a client makes no request.
    monkeypatch.setattr(b2_client.settings, "b2_region", "placeholder-region-1")
    b2_client.get_s3_client.cache_clear()
    client = b2_client.get_s3_client()
    assert TOKEN in client.meta.config.user_agent_extra
