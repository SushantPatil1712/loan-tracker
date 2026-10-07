import pytest
from fastapi.testclient import TestClient

import db
from main import app


@pytest.fixture
def client(tmp_path):
    """Each test gets its own empty database file, so tests never affect each other."""
    path = str(tmp_path / "test.db")

    def override():
        conn = db.connect(path)
        db.init_db(conn)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[db.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
