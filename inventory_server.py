#!/usr/bin/env python3
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
PORT = int(os.getenv('PORT', '8080'))

class Handler(BaseHTTPRequestHandler):
    server_version = 'ZeliInventoryDemo/0.1'

    def send_file(self, name, ctype='text/html; charset=utf-8'):
        path = STATIC / name
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            body = b'{"ok":true,"service":"zeli-inventory-demo"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ('/', '/index.html', '/demo', '/demo.html', '/scanner-test', '/scanner-test.html'):
            return self.send_file('scanner-test.html')
        self.send_error(404)

if __name__ == '__main__':
    print(f'Zeli inventory demo listening on :{PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
