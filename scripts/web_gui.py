#!/usr/bin/env python3
"""Local browser dashboard for RepoBundle (standard library only)."""
import argparse
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from export_repo import default_output_path, export_repository
from import_repo import restore_repository

STATIC = Path(__file__).parent / 'static'


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.state = {'status': 'idle', 'mode': 'export', 'summary': {}, 'logs': []}

    def run_job(self, mode, source, destination):
        def log(message):
            with self.lock:
                self.state['logs'] = (self.state['logs'] + [str(message)])[-300:]

        def progress(summary):
            with self.lock:
                self.state['summary'] = summary

        try:
            if mode == 'export':
                result = export_repository(source, default_output_path(source, destination), log, progress)
            else:
                result = restore_repository(source, destination, log, progress)
            with self.lock:
                self.state.update(status='completed', summary=result)
        except Exception as exc:
            log(str(exc))
            with self.lock:
                self.state['status'] = 'failed'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data, mime='application/json'):
        body = json.dumps(data).encode() if mime == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        host = '127.0.0.1:{}'.format(self.server.server_port)
        if self.headers.get('Host') != host:
            self.reply(403, {'error': 'Invalid host'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            self.reply(403, {'error': 'Invalid origin'})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        route = urlsplit(self.path).path
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if route in files:
            name, mime = files[route]
            self.reply(200, (STATIC / name).read_bytes(), mime)
        elif route == '/api/bootstrap':
            self.reply(200, {'token': self.server.token, 'cwd': str(Path.cwd()), 'home': str(Path.home())})
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.authorized():
            return
        if not secrets.compare_digest(self.headers.get('X-RepoBundle-Token', ''), self.server.token):
            self.reply(403, {'error': 'Invalid session'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected an object')
            route = urlsplit(self.path).path
            if route == '/api/state':
                with self.server.lock:
                    snapshot = json.loads(json.dumps(self.server.state))
                self.reply(200, snapshot)
            elif route == '/api/browse':
                path = Path(data.get('path') or Path.cwd()).expanduser().resolve()
                if not path.is_dir():
                    raise ValueError('Choose an existing directory')
                entries = []
                for child in path.iterdir():
                    if not child.name.startswith('.') and (child.is_dir() or child.suffix.lower() == '.txt'):
                        entries.append({'name': child.name, 'path': str(child), 'directory': child.is_dir()})
                entries.sort(key=lambda entry: (not entry['directory'], entry['name'].lower()))
                self.reply(200, {'path': str(path), 'parent': str(path.parent), 'entries': entries})
            elif route == '/api/run':
                mode = data.get('mode')
                if mode not in ('export', 'import'):
                    raise ValueError('Choose export or import')
                if not data.get('source') or not data.get('destination'):
                    raise ValueError('Choose a source and destination')
                source = Path(data['source']).expanduser().resolve()
                destination = Path(data['destination']).expanduser().resolve()
                if mode == 'export' and not source.is_dir():
                    raise ValueError('Repository must be an existing directory')
                if mode == 'import' and not source.is_file():
                    raise ValueError('Bundle must be an existing file')
                if destination.exists() and not destination.is_dir():
                    raise ValueError('Destination must be a directory')
                if mode == 'import' and destination.exists() and any(destination.iterdir()):
                    raise ValueError('Choose an empty or new restore folder to avoid overwriting files')
                with self.server.lock:
                    if self.server.state['status'] == 'running':
                        self.reply(409, {'error': 'A job is already running'})
                        return
                    self.server.state = {'status': 'running', 'mode': mode, 'summary': {}, 'logs': []}
                threading.Thread(target=self.server.run_job, args=(mode, source, destination), daemon=True).start()
                self.reply(202, {'status': 'running'})
            else:
                self.reply(404, {'error': 'Not found'})
        except (ValueError, OSError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=7790)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    try:
        server = Dashboard(('127.0.0.1', args.port))
    except OSError as exc:
        parser.exit(1, 'Cannot start dashboard: {}. Try --port with another port.\n'.format(exc))
    url = 'http://127.0.0.1:{}'.format(args.port)
    print('RepoBundle: {} (Ctrl+C to stop)'.format(url), flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
