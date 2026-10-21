"""HTTP boundary tests for the portable phone microphone blueprint."""

import importlib.util
import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, abort, request

ROOT = Path(__file__).resolve().parents[5] / "app/build/generated/python"
auth = types.ModuleType("pikaraoke.lib.auth")


def public(view):
    view.pika_public = True
    return view


auth.public = public
package = types.ModuleType("pikaraoke")
library = types.ModuleType("pikaraoke.lib")
with patch.dict(
    sys.modules, {"pikaraoke": package, "pikaraoke.lib": library, "pikaraoke.lib.auth": auth}
):
    spec = importlib.util.spec_from_file_location(
        "pikaraoke.lib.phone_mics", ROOT / "pikaraoke/lib/phone_mics.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

PhoneMicError, install = module.PhoneMicError, module.install


class FakeBackend:
    def __init__(self, certificate: str) -> None:
        self.certificate = certificate
        self.calls: list[tuple[object, ...]] = []

    def config(self):
        return {
            "secure_url": "https://tv:8444/mic",
            "ca_url": "/mic/ca.crt",
            "ca_fingerprint": "AA:BB",
            "base_path": "",
        }

    def certificate_path(self):
        return self.certificate

    def call(self, operation, *args):
        self.calls.append((operation, *args))
        if operation == "status":
            return {"max": 4, "active": []}
        if operation == "join":
            return {"id": "private-token", "slot": 1, "max": 4}
        if operation == "missing":
            raise PhoneMicError("Microphone disconnected. Slide up to reconnect.", 404)
        return None


class PhoneMicRoutes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ca = Path(self.temp.name) / "ca.crt"
        self.ca.write_bytes(b"public certificate only")
        self.backend = FakeBackend(str(self.ca))
        app = Flask(__name__, template_folder=str(ROOT / "pikaraoke/templates"))

        @app.before_request
        def upstream_gate():
            view = app.view_functions.get(request.endpoint)
            if view and not getattr(view, "pika_public", False):
                abort(403)

        install(app, self.backend)
        self.app, self.client = app, app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def post(self, path="", data=None, **kwargs):
        return self.client.post(
            "/api/phone-mics" + path, json=data or {}, base_url="https://tv:8443", **kwargs
        )

    def test_public_status_certificate_and_template(self):
        self.assertTrue(self.app.jinja_env.globals["phone_mics_available"])
        page = self.client.get("/mic")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="mic-toggle"', page.text)
        status = self.client.get("/api/phone-mics")
        self.assertEqual(status.status_code, 200)
        self.assertNotIn("private-token", status.text)
        cert = self.client.get("/mic/ca.crt")
        self.assertEqual(cert.data, self.ca.read_bytes())
        self.assertEqual(cert.headers["Cache-Control"], "no-store")
        cert.close()
        self.assertEqual(self.client.get("/mic/ca-key.pem").status_code, 404)

    def test_tls_origin_and_name_validation(self):
        self.assertEqual(self.client.post("/api/phone-mics", json={"name": "A"}).status_code, 403)
        self.assertEqual(
            self.post(data={"name": "A"}, headers={"Origin": "https://other.test"}).status_code, 403
        )
        for name in ["", "a" * 49, 7, None]:
            self.assertEqual(self.post(data={"name": name}).status_code, 400)
        self.assertEqual(self.post(data={"name": "  Singer  "}).status_code, 201)
        self.assertIn(("join", "Singer"), self.backend.calls)

    def test_asset_urls_change_for_same_size_updates_with_fixed_timestamps(self):
        def page_config():
            page = self.client.get("/mic").text
            config = json.loads(re.search(r"window.phoneMicConfig = (.*);", page).group(1))
            for asset in ("phone-mic.js", "phone-mic.css"):
                self.assertIn(f"{asset}?v={config['asset_version']}", page)
            return config

        original = Path.read_bytes

        def previous_worklet(path):
            data = original(path)
            return (
                data.replace(b"packetSize = 128", b"packetSize = 256")
                if path.name == "phone-mic-worklet.js"
                else data
            )

        current = page_config()
        with patch.object(Path, "read_bytes", previous_worklet):
            previous = page_config()
        self.assertNotEqual(current["asset_version"], previous["asset_version"])

    def test_controls_reject_invalid_and_nonfinite_values(self):
        for data in [
            {"gain": -1},
            {"gain": 2.01},
            {"gain": True},
            {"gain": float("nan")},
            {"reverb": 4},
            {"reverb": 1.2},
            {"muted": "yes"},
        ]:
            self.assertEqual(self.post("/token/controls", data).status_code, 400)
        self.assertEqual(
            self.post("/token/controls", {"gain": 0.3, "muted": True, "reverb": 2}).status_code, 200
        )
        self.assertIn(("controls", "token", 0.3, True, 2), self.backend.calls)

    def test_gain_accepts_boost_up_to_double_amplitude(self):
        self.assertEqual(self.post("/token/controls", {"gain": 2}).status_code, 200)
        self.assertIn(("controls", "token", 2, False, 0), self.backend.calls)

    def test_only_data_channel_offers_and_bounded_requests(self):
        for sdp in [
            "bogus",
            "m=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\nm=audio 9 RTP/AVP 0",
            "m=application " + "x" * 61000,
        ]:
            self.assertEqual(self.post("/token/offer", {"sdp": sdp}).status_code, 400)
        self.assertEqual(
            self.post("/token/offer", {"sdp": "m=application " + "x" * 66000}).status_code, 413
        )
        self.assertNotIn(("answer", "token"), self.backend.calls)

    def test_phone_mic_errors_are_sanitized(self):
        class ErrorBackend(FakeBackend):
            def call(self, operation, *args):
                raise PhoneMicError("Microphone disconnected. Slide up to reconnect.", 404)

        self.app = Flask(__name__)
        install(self.app, ErrorBackend(str(self.ca)))
        self.client = self.app.test_client()
        response = self.post("/missing/heartbeat")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Slide up", response.text)


if __name__ == "__main__":
    unittest.main()
