"""Small threading replacements for upstream's gevent execution seams."""
from threading import Thread
from werkzeug.serving import make_server

Greenlet = Thread
server = None


def spawn(function, *args, **kwargs):
    worker = Thread(target=function, args=args, kwargs=kwargs, daemon=True)
    worker.start()
    return worker


class WSGIServer:
    def __init__(self, address, app, **kwargs):
        self.httpd = make_server(*address, app, threaded=True)

    def start(self):
        global server
        server = self.httpd
        spawn(self.httpd.serve_forever)


def stop_server():
    if server:
        server.shutdown()
