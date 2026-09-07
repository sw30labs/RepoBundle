import json
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from web_gui import Dashboard


@pytest.fixture
def dashboard():
    server = Dashboard(('127.0.0.1', 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, path, data=None, **headers):
    if data is not None:
        headers.setdefault('X-RepoBundle-Token', server.token)
        headers['Content-Type'] = 'application/json'
    req = Request('http://127.0.0.1:{}{}'.format(server.server_port, path),
                  data=None if data is None else json.dumps(data).encode(), headers=headers)
    with urlopen(req, timeout=5) as response:
        body = response.read()
        return json.loads(body) if response.headers['Content-Type'] == 'application/json' else body


def completed(server):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = request(server, '/api/state', {})
        if state['status'] != 'running':
            assert state['status'] == 'completed', state
            return state
        time.sleep(.01)
    pytest.fail('Job did not finish')


def test_browser_export_restore(dashboard, tmp_path):
    source = tmp_path / 'source with spaces'
    source.mkdir()
    (source / 'hello.txt').write_bytes(b'hello\n')
    (source / 'binary.bin').write_bytes(b'\x00\xff\x01')
    (source / '.secret').write_text('excluded')
    assert b'repobundle' in request(dashboard, '/')
    assert request(dashboard, '/api/bootstrap')['token'] == dashboard.token
    assert b'async function api' in request(dashboard, '/app.js')
    listing = request(dashboard, '/api/browse', {'path': str(tmp_path)})
    assert listing['entries'][0]['name'] == source.name
    request(dashboard, '/api/run', {'mode': 'export', 'source': str(source), 'destination': str(tmp_path / 'bundles')})
    state = completed(dashboard)
    assert state['summary']['files'] == 2
    bundle = state['summary']['output_path']
    restored = tmp_path / 'restored'
    request(dashboard, '/api/run', {'mode': 'import', 'source': bundle, 'destination': str(restored)})
    assert completed(dashboard)['summary']['files'] == 2
    assert (restored / 'hello.txt').read_bytes() == b'hello\n'
    assert (restored / 'binary.bin').read_bytes() == b'\x00\xff\x01'
    with pytest.raises(HTTPError) as exc:
        request(dashboard, '/api/run', {'mode': 'import', 'source': bundle, 'destination': str(restored)})
    assert exc.value.code == 400


def test_rejects_foreign_requests_and_invalid_paths(dashboard, tmp_path):
    for headers in [{'X-RepoBundle-Token': 'invalid'}, {'Origin': 'https://example.com'}, {'Host': 'example.com'}]:
        with pytest.raises(HTTPError) as exc:
            request(dashboard, '/api/state', {}, **headers)
        assert exc.value.code == 403
    with pytest.raises(HTTPError) as exc:
        request(dashboard, '/api/run', {'mode': 'export', 'source': str(tmp_path / 'missing'), 'destination': str(tmp_path)})
    assert exc.value.code == 400
    with dashboard.lock:
        dashboard.state['status'] = 'running'
    with pytest.raises(HTTPError) as exc:
        request(dashboard, '/api/run', {'mode': 'export', 'source': str(tmp_path), 'destination': str(tmp_path)})
    assert exc.value.code == 409
