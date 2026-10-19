"""Phone microphone pages, scoped room APIs, and a second HTTPS listener."""
import json
import math
import ssl
from pathlib import Path
from urllib.parse import urlsplit

_context = None
_tls = None
_ssl_context = None
_server = None


def _host():
    from org.pikaraoke.tv import PhoneMicHost
    return PhoneMicHost.get(_context)


def _address():
    from org.pikaraoke.tv import AndroidPlatform
    return str(AndroidPlatform.localIp(_context))


def secure_url():
    return f'https://{_address()}:8443/mic'


def refresh_certificate():
    global _tls
    if _context is None:
        return
    from org.pikaraoke.tv import PhoneMicCertificates
    _tls = json.loads(str(PhoneMicCertificates.ensure(_context, _address())))
    if _ssl_context is not None:
        _ssl_context.load_cert_chain(_tls['cert'], _tls['key'])


def install(app, context):
    global _context, _ssl_context
    from flask import Blueprint, abort, jsonify, render_template, request, send_file
    from pikaraoke.lib.auth import public

    _context = context
    refresh_certificate()
    _ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    _ssl_context.load_cert_chain(_tls['cert'], _tls['key'])
    bp = Blueprint('phone_mics', __name__)

    @bp.before_request
    def check_origin():
        request.max_content_length = 65536
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                abort(403)
            if not request.is_secure:
                return jsonify(error='Open the secure microphone page first.'), 403

    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def body():
        if request.content_length and request.content_length > 65536:
            abort(413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400)
        return data

    def call(operation, *args):
        try:
            value = getattr(_host(), operation)(*args)
            return json.loads(str(value)) if value is not None else {'ok': True}
        except Exception as exc:
            # Only public, actionable errors; native exception text can include SDP.
            kind = str(type(exc))
            if 'IllegalArgumentException' in kind:
                return jsonify(error='Microphone disconnected. Tap the mic to reconnect.'), 404
            if operation == 'join':
                return jsonify(error='All four microphones are in use. Try again when someone disconnects.'), 409
            return jsonify(error='Microphone connection failed. Disconnect and try again.'), 503

    @bp.get('/mic')
    @public
    def page():
        return render_template('android/phone-mic.html', mic_config={
            'secure_url': secure_url(), 'ca_url': '/mic/ca.crt',
            'ca_fingerprint': _tls['fingerprint'], 'room_name': 'PiKaraoke', 'base_path': '',
        })

    @bp.get('/mic/ca.crt')
    @public
    def certificate():
        # Deliberately fixed public file: no caller-provided path or private key.
        return send_file(_tls['ca'], mimetype='application/x-x509-ca-cert',
                         as_attachment=True, download_name='PiKaraoke-TV-CA.crt')

    @bp.get('/api/phone-mics')
    @public
    def status():
        result = call('status')
        if not isinstance(result, dict):
            return result
        k = app.config.get('KARAOKE_INSTANCE')
        now = k.get_now_playing() if k is not None else {}
        result.update(secure_url=secure_url(), ca_fingerprint=_tls['fingerprint'],
                      now_playing={'title': now.get('now_playing') or '',
                                   'user': now.get('now_playing_user') or '',
                                   'is_paused': now.get('is_paused', False)})
        return jsonify(result)

    @bp.post('/api/phone-mics')
    @public
    def join():
        data = body()
        name = data.get('name', 'Singer')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48:
            return jsonify(error='Enter a name using 1–48 characters.'), 400
        result = call('join', name.strip())
        return (jsonify(result), 201) if isinstance(result, dict) else result

    @bp.post('/api/phone-mics/<identity>/offer')
    @public
    def offer(identity):
        sdp = body().get('sdp')
        if not isinstance(sdp, str) or len(sdp) > 60000 or 'm=application ' not in sdp \
                or any(line.startswith(('m=audio ', 'm=video ')) for line in sdp.splitlines()):
            return jsonify(error='Invalid microphone connection.'), 400
        return call('answer', identity, sdp)

    @bp.post('/api/phone-mics/<identity>/controls')
    @public
    def controls(identity):
        data = body()
        gain, muted, reverb = data.get('gain', .65), data.get('muted', False), data.get('reverb', 0)
        if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not math.isfinite(gain) \
                or not 0 <= gain <= 1 or not isinstance(muted, bool) \
                or type(reverb) is not int or not 0 <= reverb <= 3:
            return jsonify(error='Invalid microphone settings.'), 400
        return call('controls', identity, gain, muted, reverb)

    @bp.post('/api/phone-mics/<identity>/heartbeat')
    @public
    def heartbeat(identity):
        return call('heartbeat', identity)

    @bp.route('/api/phone-mics/<identity>', methods=['DELETE'])
    @bp.post('/api/phone-mics/<identity>/leave')
    @public
    def leave(identity):
        return call('leave', identity)

    app.register_blueprint(bp)


def start_https(app):
    global _server
    from werkzeug.serving import make_server
    from android_runtime.compat import spawn
    _server = make_server('0.0.0.0', 8443, app, threaded=True, ssl_context=_ssl_context)
    spawn(_server.serve_forever)


def stop():
    global _server
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
    from org.pikaraoke.tv import PhoneMicHost
    PhoneMicHost.stopAll()
