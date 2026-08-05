from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *args):
        pass
server = ThreadingHTTPServer(('127.0.0.1', 8011), Handler)
print('bound')
server.serve_forever()
