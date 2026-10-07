"""Unit tests for the MQTT transport shared by the source and the destination.

The password resolution is the part worth pinning: it decides where a secret is
read from, and getting it wrong either leaks the secret into a versioned file or
fails against the broker for a reason nobody can see from the logs.
"""

from __future__ import annotations

import asyncio

import pytest

aiomqtt = pytest.importorskip("aiomqtt")

from cod3s_data.core.mqtt_client import (  # noqa: E402
    RECONNECT_BACKOFF_MAX_S,
    MQTTConnection,
    ReconnectBackoff,
    require_aiomqtt,
)


class TestPasswordResolution:
    def test_no_password_configured(self):
        assert MQTTConnection().resolve_password() is None

    def test_inline_password(self):
        assert MQTTConnection(password="s3cret").resolve_password() == "s3cret"

    def test_environment_variable(self, monkeypatch):
        monkeypatch.setenv("COD3S_TEST_MQTT_PASSWORD", "from-env")
        conn = MQTTConnection(password_env="COD3S_TEST_MQTT_PASSWORD")
        assert conn.resolve_password() == "from-env"

    def test_file_wins_over_env_and_inline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COD3S_TEST_MQTT_PASSWORD", "from-env")
        secret = tmp_path / "broker.pwd"
        secret.write_text("from-file\n", encoding="utf-8")

        conn = MQTTConnection(
            password="inline",
            password_env="COD3S_TEST_MQTT_PASSWORD",
            password_file=str(secret),
        )
        assert conn.resolve_password() == "from-file"

    def test_env_wins_over_inline(self, monkeypatch):
        monkeypatch.setenv("COD3S_TEST_MQTT_PASSWORD", "from-env")
        conn = MQTTConnection(password="inline", password_env="COD3S_TEST_MQTT_PASSWORD")
        assert conn.resolve_password() == "from-env"

    def test_missing_variable_is_an_error_not_a_fallback(self, monkeypatch):
        monkeypatch.delenv("COD3S_TEST_MQTT_PASSWORD", raising=False)
        conn = MQTTConnection(password="inline", password_env="COD3S_TEST_MQTT_PASSWORD")

        with pytest.raises(ValueError, match="COD3S_TEST_MQTT_PASSWORD"):
            conn.resolve_password()

    def test_unreadable_file_is_an_error(self, tmp_path):
        conn = MQTTConnection(password_file=str(tmp_path / "absent.pwd"))
        with pytest.raises(ValueError, match="unreadable"):
            conn.resolve_password()

    def test_empty_file_is_an_error(self, tmp_path):
        secret = tmp_path / "empty.pwd"
        secret.write_text("   \n", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            MQTTConnection(password_file=str(secret)).resolve_password()


class TestSecretsStayOut:
    def test_password_is_absent_from_repr(self):
        conn = MQTTConnection(username="gemini", password="s3cret")
        assert "s3cret" not in repr(conn)
        assert "gemini" in repr(conn)

    def test_describe_carries_no_secret(self):
        conn = MQTTConnection(username="gemini", password="s3cret", tls=True)
        described = conn.describe()

        assert "s3cret" not in str(described)
        assert described == {"host": "localhost", "port": 1883, "tls": True, "authenticated": True}


class TestClientConstruction:
    """``aiomqtt.Client`` grabs the running loop in its constructor, so every
    one of these has to be async even though nothing connects."""

    async def test_host_and_port_reach_the_client(self):
        client = MQTTConnection(host="broker", port=1884).client()

        assert client._hostname == "broker"
        assert client._port == 1884
        assert client._keepalive == 60

    async def test_credentials_reach_the_client(self, monkeypatch):
        monkeypatch.setenv("COD3S_TEST_MQTT_PASSWORD", "from-env")
        conn = MQTTConnection(username="gemini", password_env="COD3S_TEST_MQTT_PASSWORD")

        client = conn.client()

        assert client._client._username == b"gemini"
        assert client._client._password == b"from-env"

    async def test_no_credentials_when_none_configured(self):
        client = MQTTConnection().client()
        assert client._client._username is None

    async def test_client_id_is_used_when_given(self):
        client = MQTTConnection(client_id="gemini-writer").client()
        assert client.identifier == "gemini-writer"

    async def test_tls_builds_parameters(self, tmp_path):
        ca = tmp_path / "ca.pem"
        conn = MQTTConnection(
            tls=True, tls_ca=str(ca), tls_cert="/tmp/c.pem", tls_key="/tmp/k.pem", tls_insecure=True
        )

        client = conn.client()

        assert client._tls_params is not None
        assert client._tls_params.ca_certs == str(ca)
        assert client._tls_params.certfile == "/tmp/c.pem"
        assert client._tls_params.keyfile == "/tmp/k.pem"
        assert client._tls_insecure is True

    async def test_no_tls_parameters_by_default(self):
        assert MQTTConnection().client()._tls_params is None


class TestRequireExtra:
    def test_message_names_the_component_and_the_extra(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "aiomqtt", None)
        with pytest.raises(ImportError, match=r"MQTTDestination.*cod3s-data\[mqtt\]"):
            require_aiomqtt("MQTTDestination")


class TestReconnectBackoff:
    async def test_delay_doubles_and_is_capped(self):
        backoff = ReconnectBackoff("MQTTSource")
        conn = MQTTConnection()
        delays: list[float] = []

        async def fake_sleep(delay, _is_running):
            delays.append(delay)

        import cod3s_data.core.mqtt_client as module

        original = module._sleep_while_running
        module._sleep_while_running = fake_sleep
        try:
            for _ in range(10):
                await backoff.wait(aiomqtt.MqttError("gone"), conn, lambda: True)
        finally:
            module._sleep_while_running = original

        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[-1] == RECONNECT_BACKOFF_MAX_S

    async def test_reset_forgets_past_failures(self):
        backoff = ReconnectBackoff("MQTTSource")
        conn = MQTTConnection()
        delays: list[float] = []

        async def fake_sleep(delay, _is_running):
            delays.append(delay)

        import cod3s_data.core.mqtt_client as module

        original = module._sleep_while_running
        module._sleep_while_running = fake_sleep
        try:
            await backoff.wait(aiomqtt.MqttError("gone"), conn, lambda: True)
            await backoff.wait(aiomqtt.MqttError("gone"), conn, lambda: True)
            backoff.reset()
            await backoff.wait(aiomqtt.MqttError("gone"), conn, lambda: True)
        finally:
            module._sleep_while_running = original

        assert delays == [1.0, 2.0, 1.0]

    async def test_a_stopping_component_does_not_serve_its_whole_wait(self):
        from cod3s_data.core.mqtt_client import _sleep_while_running

        started = asyncio.get_running_loop().time()
        await _sleep_while_running(RECONNECT_BACKOFF_MAX_S, lambda: False)

        assert asyncio.get_running_loop().time() - started < 1.0
