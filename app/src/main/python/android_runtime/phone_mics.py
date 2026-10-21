"""Android TV receiver and HTTPS listener for :mod:`pikaraoke.lib.phone_mics`."""

from __future__ import annotations

import json
import ssl
import threading
from typing import Any, Callable

from pikaraoke.lib.phone_mics import PhoneMicError
from pikaraoke.lib.phone_mics import install as install_routes

# The org.pikaraoke.tv classes are supplied by Chaquopy on Android.
_context: Any = None
_address_provider: Callable[[], str] | None = None
_tls: dict[str, str] | None = None
_ssl_context: ssl.SSLContext | None = None
_server: Any = None


def _address() -> str:
    if _address_provider is None:
        raise RuntimeError("Phone microphone integration is not installed.")
    return str(_address_provider())


def _host() -> Any:
    from org.pikaraoke.tv import PhoneMicHost  # pylint: disable=import-error

    return PhoneMicHost.get(_context)


def refresh_certificate() -> None:
    global _tls
    if _context is None:
        return
    from org.pikaraoke.tv import PhoneMicCertificates  # pylint: disable=import-error

    _tls = json.loads(str(PhoneMicCertificates.ensure(_context, _address())))
    if _ssl_context is not None:
        _ssl_context.load_cert_chain(_tls["cert"], _tls["key"])


class _AndroidBackend:
    def __init__(self, app: Any) -> None:
        self.app = app

    def config(self) -> dict[str, Any]:
        assert _tls is not None
        base_path = str(self.app.config.get("PIKARAOKE_BASE_PATH", "")).rstrip("/")
        return {
            "secure_url": f"https://{_address()}:8444{base_path}/mic",
            "ca_fingerprint": _tls["fingerprint"],
            "base_path": base_path,
            "ca_url": f"{base_path}/mic/ca.crt",
            "room_name": "PiKaraoke",
        }

    def certificate_path(self) -> str:
        assert _tls is not None
        return _tls["ca"]

    def call(self, operation: str, *args: Any) -> dict[str, Any] | None:
        try:
            host = _host()
            if operation in ("join", "status"):
                preferences = self.app.config["KARAOKE_INSTANCE"].preferences
                with preferences.mutation_lock:
                    host.setMaxMics(preferences.get_or_default("max_phone_mics"))
                    value = getattr(host, operation)(*args)
            else:
                value = getattr(host, operation)(*args)
            return json.loads(str(value)) if value is not None else None
        except Exception as exc:
            # Do not expose native exception text: it can contain SDP.
            if "IllegalArgumentException" in str(type(exc)):
                raise PhoneMicError(
                    "Microphone disconnected. Slide up to reconnect.", 404
                ) from None
            if operation == "join":
                raise PhoneMicError(
                    "All microphones are in use. Try again when someone disconnects.",
                    409,
                ) from None
            raise PhoneMicError(
                "Microphone connection failed. Disconnect and try again.", 503
            ) from None


def install(app: Any, context: Any, address_provider: Callable[[], str]) -> None:
    """Register phone mic routes against an Android TV receiver."""
    global _context, _address_provider, _ssl_context
    _context, _address_provider = context, address_provider
    refresh_certificate()
    _ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    assert _tls is not None
    _ssl_context.load_cert_chain(_tls["cert"], _tls["key"])
    install_routes(app, _AndroidBackend(app))


def start_https(app: Any) -> None:
    global _server
    from werkzeug.serving import make_server

    refresh_certificate()
    _server = make_server("0.0.0.0", 8444, app, threaded=True, ssl_context=_ssl_context)
    threading.Thread(target=_server.serve_forever, name="PiKaraoke HTTPS", daemon=True).start()


def stop() -> None:
    global _server
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
    from org.pikaraoke.tv import PhoneMicHost  # pylint: disable=import-error

    PhoneMicHost.stopAll()
