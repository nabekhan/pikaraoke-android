"""Small threading replacements for upstream's gevent execution seams."""
from threading import Thread
from werkzeug.serving import make_server

Greenlet = Thread
server = None
servers_ready = False


def spawn(function, *args, **kwargs):
    worker = Thread(target=function, args=args, kwargs=kwargs, daemon=True)
    worker.start()
    return worker


class WSGIServer:
    def __init__(self, address, app, **kwargs):
        self.httpd = make_server(*address, app, threaded=True)

    def start(self):
        global server, servers_ready
        server = self.httpd
        from android_runtime.phone_mics import start_https
        start_https(self.httpd.app)
        spawn(self.httpd.serve_forever)
        servers_ready = True


def stop_server():
    global servers_ready
    servers_ready = False
    from android_runtime.phone_mics import stop
    stop()
    if server:
        server.shutdown()
