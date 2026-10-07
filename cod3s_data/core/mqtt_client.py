"""Transport shared by the MQTT source and the MQTT destination.

The two MQTT bricks face the same broker and must therefore offer the same
connection surface: the pipeline that reads `gemini/egm` over TLS should be able
to publish its alarms over that same TLS, with the same credentials, spelled the
same way in YAML. Keeping that surface here is what makes the pair symmetric —
and it keeps the reconnection policy in one place instead of two.

Three things live here:

- :class:`MQTTConnection`, every connection option, with the password resolved
  out of the environment or a file rather than read from the pipeline file;
- :func:`require_aiomqtt`, the single actionable message for the missing extra;
- :class:`ReconnectBackoff`, the schedule both bricks retry on.

Requires the ``mqtt`` extra::

    pip install cod3s-data[mqtt]
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:  # pragma: no cover - typing only
    import aiomqtt

_logger = structlog.get_logger()

#: First wait after a dropped connection, in seconds. Doubles per attempt.
RECONNECT_BACKOFF_START_S = 1.0

#: Ceiling for that backoff. A broker that stays down is retried every minute
#: rather than every hour: operators restart brokers, and the pipeline should
#: pick the stream back up on its own once they do.
RECONNECT_BACKOFF_MAX_S = 60.0


def require_aiomqtt(component: str) -> Any:
    """Import ``aiomqtt``, or raise an error that says how to get it.

    Args:
        component: Class name quoted in the message, so the user knows which
            component asked for the extra.

    Returns:
        The ``aiomqtt`` module.

    Raises:
        ImportError: If the ``mqtt`` extra is not installed
    """
    try:
        import aiomqtt
    except ImportError:
        raise ImportError(
            f"{component} requires the 'mqtt' extra: pip install cod3s-data[mqtt]"
        ) from None
    return aiomqtt


@dataclass(frozen=True)
class MQTTConnection:
    """Everything needed to open a connection to an MQTT broker.

    The password is never meant to be written in the pipeline file. The YAML
    loader does not expand ``${VAR}``, so a password spelled there would be a
    literal — and pipeline files are versioned. Hence ``password_env`` and
    ``password_file``, which name where the secret lives instead of carrying it.
    ``password`` remains for a local broker or a test, and is kept out of
    ``repr()`` so it cannot reach a log line through a component dump.

    Attributes:
        host: Broker hostname
        port: Broker TCP port
        client_id: MQTT client identifier; None lets the library generate one.
            Give a stable one to a subscriber that needs a persistent session.
        keepalive: Seconds between pings on an idle connection
        username: User name, when the broker authenticates
        password: Password, in clear; prefer ``password_env`` or ``password_file``
        password_env: Environment variable holding the password
        password_file: File holding the password (whitespace is stripped)
        tls: Wrap the connection in TLS
        tls_ca: Certificate authority bundle used to verify the broker
        tls_cert: Client certificate, for mutual TLS
        tls_key: Private key matching ``tls_cert``
        tls_insecure: Skip hostname verification — for a self-signed broker on a
            closed network, never in the open
    """

    host: str = "localhost"
    port: int = 1883
    client_id: str | None = None
    keepalive: int = 60
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    password_env: str | None = None
    password_file: str | None = None
    tls: bool = False
    tls_ca: str | None = None
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_insecure: bool = False

    def resolve_password(self) -> str | None:
        """Return the password, looked up where it actually lives.

        Precedence is ``password_file``, then ``password_env``, then
        ``password``: the further a secret is from the pipeline file, the more
        it is trusted. A named source that turns out to be empty is an error
        rather than a silent fallback — a typo in a variable name would
        otherwise surface as an authentication failure against the broker.

        Returns:
            The password, or None when none is configured.

        Raises:
            ValueError: If the named file or variable is missing or empty
        """
        if self.password_file:
            path = Path(self.password_file).expanduser()
            try:
                secret = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError(
                    f"password_file {self.password_file!r} is unreadable: {exc}"
                ) from None
            if not secret:
                raise ValueError(f"password_file {self.password_file!r} is empty")
            return secret
        if self.password_env:
            secret = os.environ.get(self.password_env, "")
            if not secret:
                raise ValueError(f"environment variable {self.password_env!r} is unset or empty")
            return secret
        return self.password

    def client(self, **extra: Any) -> aiomqtt.Client:
        """Build an ``aiomqtt`` client for this connection.

        Args:
            **extra: Passed through to ``aiomqtt.Client`` — used by callers that
                need a setting this class does not expose.

        Returns:
            An unconnected client; use it as an async context manager.

        Raises:
            ImportError: If the ``mqtt`` extra is not installed
            ValueError: If a named password source is missing or empty
        """
        aiomqtt = require_aiomqtt("MQTT components")

        kwargs: dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "keepalive": self.keepalive,
            **extra,
        }
        if self.client_id is not None:
            kwargs["identifier"] = self.client_id
        if self.username is not None:
            kwargs["username"] = self.username
        password = self.resolve_password()
        if password is not None:
            kwargs["password"] = password
        if self.tls:
            kwargs["tls_params"] = aiomqtt.TLSParameters(
                ca_certs=self.tls_ca,
                certfile=self.tls_cert,
                keyfile=self.tls_key,
            )
            if self.tls_insecure:
                kwargs["tls_insecure"] = True

        return aiomqtt.Client(**kwargs)  # type: ignore[no-any-return]

    def describe(self) -> dict[str, Any]:
        """Connection summary fit for a log line — no secret in it."""
        return {
            "host": self.host,
            "port": self.port,
            "tls": self.tls,
            "authenticated": self.username is not None,
        }


class ReconnectBackoff:
    """The wait between two connection attempts, shared by both MQTT bricks.

    Without a retry policy, an ``MqttError`` propagates out of a source's
    ``produce()`` and the framework reports the source as *completed*: a broker
    restart stops the ingestion while the pipeline still looks healthy. The two
    bricks reach that policy by different routes — the source loops on its
    subscription, the destination leans on the retry loop every ``Destination``
    already has — so what is shared is the schedule, not the control flow.

    Args:
        component: Name used in log events
    """

    def __init__(self, component: str) -> None:
        self.component = component
        self._delay = RECONNECT_BACKOFF_START_S

    def reset(self) -> None:
        """Forget past failures — call once a connection is established."""
        self._delay = RECONNECT_BACKOFF_START_S

    async def wait(
        self,
        error: BaseException,
        conn: MQTTConnection,
        is_running: Callable[[], bool],
    ) -> None:
        """Log the drop, wait, and lengthen the next wait.

        Args:
            error: The error that broke the connection
            conn: Connection settings, for the log line
            is_running: Checked while waiting, so a stop request cuts the wait
                short instead of holding a stopping pipeline for a minute
        """
        _logger.warning(
            "mqtt.disconnected",
            component=self.component,
            error=str(error),
            retry_in_s=self._delay,
            **conn.describe(),
        )
        await _sleep_while_running(self._delay, is_running)
        self._delay = min(self._delay * 2, RECONNECT_BACKOFF_MAX_S)


async def _sleep_while_running(delay: float, is_running: Callable[[], bool]) -> None:
    """Sleep, but give up as soon as the component is asked to stop.

    A flat ``asyncio.sleep(60)`` would keep a stopping pipeline waiting for a
    minute on a broker nobody expects to come back.
    """
    deadline = asyncio.get_running_loop().time() + delay
    while is_running():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.25, remaining))
