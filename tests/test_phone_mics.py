"""HTTP boundary tests; native transport and certificates run on Android."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from flask import Flask, abort, request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phone_mics', ROOT / 'app/src/main/python/android_runtime/phone_mics.py')
mics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mics)


class PhoneMicRoutes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ca = Path(self.temp.name) / 'ca.crt'
        self.ca.write_bytes(b'public certificate only')
        auth = types.ModuleType('pikaraoke.lib.auth')
        def public(view):
            view.pika_public = True
            return view
        auth.public = public
        self.host = Mock()
        self.host.status.return_value = json.dumps({'max': 4, 'active': []})
        self.host.join.return_value = json.dumps({'id': 'private-token', 'slot': 1, 'max': 4})
        self.host.controls.return_value = None
        self.host.leave.return_value = None
        self.host.heartbeat.return_value = None
        self.patches = [patch.dict(sys.modules, {'pikaraoke.lib.auth': auth}),
                        patch.object(mics, 'refresh_certificate'),
                        patch.object(mics.ssl, 'SSLContext'),
                        patch.object(mics, '_address', return_value='192.168.1.20'),
                        patch.object(mics, '_host', return_value=self.host)]
        for p in self.patches: p.start()
        mics._tls = {'cert': 'private-cert', 'key': 'private-key', 'ca': str(self.ca), 'fingerprint': 'AA:BB'}
        app = Flask(__name__)
        @app.before_request
        def upstream_gate():
            view = app.view_functions.get(request.endpoint)
            if view and not getattr(view, 'pika_public', False): abort(403)
        mics.install(app, object())
        self.app, self.client = app, app.test_client()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def post(self, path='', data=None, **kwargs):
        return self.client.post('/api/phone-mics'+path, json=data or {}, base_url='https://tv:8443', **kwargs)

    def test_public_status_and_certificate_exclude_private_material(self):
        status = self.client.get('/api/phone-mics')
        self.assertEqual(status.status_code, 200)
        self.assertNotIn('private-key', status.text)
        cert = self.client.get('/mic/ca.crt')
        self.assertEqual(cert.data, self.ca.read_bytes())
        self.assertEqual(cert.headers['Cache-Control'], 'no-store')
        cert.close()
        self.assertEqual(self.client.get('/mic/ca-key.pem').status_code, 404)

    def test_tls_origin_and_name_validation(self):
        self.assertEqual(self.client.post('/api/phone-mics', json={'name':'A'}).status_code, 403)
        self.assertEqual(self.post(data={'name':'A'},headers={'Origin':'https://other.test'}).status_code,403)
        for name in ['', 'a'*49, 7, None]: self.assertEqual(self.post(data={'name':name}).status_code,400)
        joined = self.post(data={'name':'  Singer  '})
        self.assertEqual(joined.status_code,201)
        self.host.join.assert_called_once_with('Singer')

    def test_controls_reject_invalid_and_nonfinite_values(self):
        for data in [{'gain':-1},{'gain':True},{'gain':float('nan')},{'reverb':4},{'reverb':1.2},{'muted':'yes'}]:
            self.assertEqual(self.post('/token/controls',data).status_code,400)
        self.assertEqual(self.post('/token/controls',{'gain':.3,'muted':True,'reverb':2}).status_code,200)
        self.host.controls.assert_called_once_with('token',.3,True,2)

    def test_only_data_channel_offers_and_bounded_requests(self):
        for sdp in ['bogus','m=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\nm=audio 9 RTP/AVP 0','m=application '+'x'*61000]:
            self.assertEqual(self.post('/token/offer',{'sdp':sdp}).status_code,400)
        self.assertEqual(self.post('/token/offer',{'sdp':'m=application '+'x'*66000}).status_code,413)
        self.host.answer.assert_not_called()

    def test_release_and_heartbeat_are_guest_operations(self):
        self.assertEqual(self.post('/token/heartbeat').status_code,200)
        self.assertEqual(self.post('/token/leave').status_code,200)
        self.host.leave.assert_called_once_with('token')


if __name__ == '__main__': unittest.main()
