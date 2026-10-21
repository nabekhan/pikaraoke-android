"""Guest-facing phone microphone routes shared by platform integrations."""

from __future__ import annotations

import math
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from flask import Blueprint, Flask, abort, jsonify, render_template, request, send_file

from pikaraoke.lib.auth import public


class PhoneMicError(Exception):
    """A safe error that a microphone backend permits us to show to guests."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PhoneMicBackend(Protocol):
    def config(self) -> dict[str, Any]: ...
    def certificate_path(self) -> str: ...
    def call(self, operation: str, *args: Any) -> dict[str, Any] | None: ...


def install(app: Flask, backend: PhoneMicBackend) -> None:
    """Install the public UI and tightly scoped guest microphone API."""
    bp = Blueprint("phone_mics", __name__)

    @bp.before_request
    def check_origin() -> Any:
        request.max_content_length = 65536
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                abort(403)
            if not request.is_secure:
                return jsonify(error="Open the secure microphone page first."), 403
        return None

    @bp.after_request
    def no_cache(response: Any) -> Any:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def body() -> dict[str, Any]:
        if request.content_length and request.content_length > 65536:
            abort(413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400)
        return data

    def call(operation: str, *args: Any) -> Any:
        try:
            value = backend.call(operation, *args)
            return {"ok": True} if value is None else value
        except PhoneMicError as error:
            return jsonify(error=error.message), error.status_code

    @bp.get("/mic")
    @public
    def page() -> Any:
        # Packaged assets can have a fixed timestamp. File size/mtime ETags can therefore
        # stay identical after an update (for example, packet size 256 -> 128).
        assets = Path(__file__).resolve().parents[1] / "static"
        digest = sha256()
        for name in ("phone-mic.js", "phone-mic.css", "phone-mic-worklet.js"):
            digest.update((assets / name).read_bytes())
        config = {**backend.config(), "asset_version": digest.hexdigest()[:16]}
        return render_template("phone-mic.html", mic_config=config)

    @bp.get("/mic/ca.crt")
    @public
    def certificate() -> Any:
        return send_file(
            backend.certificate_path(),
            mimetype="application/x-x509-ca-cert",
            as_attachment=True,
            download_name="PiKaraoke-CA.crt",
        )

    @bp.get("/api/phone-mics")
    @public
    def status() -> Any:
        result = call("status")
        if not isinstance(result, dict):
            return result
        result.update(backend.config())
        return jsonify(result)

    @bp.post("/api/phone-mics")
    @public
    def join() -> Any:
        name = body().get("name", "Singer")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48:
            return jsonify(error="Enter a name using 1–48 characters."), 400
        result = call("join", name.strip())
        return (jsonify(result), 201) if isinstance(result, dict) else result

    @bp.post("/api/phone-mics/<identity>/offer")
    @public
    def offer(identity: str) -> Any:
        sdp = body().get("sdp")
        if (
            not isinstance(sdp, str)
            or len(sdp) > 60000
            or "m=application " not in sdp
            or any(line.startswith(("m=audio ", "m=video ")) for line in sdp.splitlines())
        ):
            return jsonify(error="Invalid microphone connection."), 400
        return call("answer", identity, sdp)

    @bp.post("/api/phone-mics/<identity>/controls")
    @public
    def controls(identity: str) -> Any:
        data = body()
        gain, muted, reverb = (
            data.get("gain", 1.0),
            data.get("muted", False),
            data.get("reverb", 0),
        )
        if (
            isinstance(gain, bool)
            or not isinstance(gain, (int, float))
            or not math.isfinite(gain)
            or not 0 <= gain <= 2
            or not isinstance(muted, bool)
            or type(reverb) is not int
            or not 0 <= reverb <= 3
        ):
            return jsonify(error="Invalid microphone settings."), 400
        return call("controls", identity, gain, muted, reverb)

    @bp.post("/api/phone-mics/<identity>/heartbeat")
    @public
    def heartbeat(identity: str) -> Any:
        return call("heartbeat", identity)

    @bp.route("/api/phone-mics/<identity>", methods=["DELETE"])
    @bp.post("/api/phone-mics/<identity>/leave")
    @public
    def leave(identity: str) -> Any:
        return call("leave", identity)

    app.register_blueprint(bp)
    app.jinja_env.globals["phone_mics_available"] = True
