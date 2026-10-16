import functools
import http.server
import threading
from pathlib import Path

import pytest

from gcc_atlas.db import connect, migrate
from gcc_atlas.seed import seed_all

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.sqlite")
    migrate(c)
    yield c
    c.close()


@pytest.fixture
def seeded(conn):
    seed_all(conn)
    return conn


@pytest.fixture(scope="session")
def fixture_server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def point_source_at(conn, key, url):
    conn.execute("UPDATE sources SET url=? WHERE source_key=?", (url, key))
    conn.commit()
