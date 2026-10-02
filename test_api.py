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


def make_borrower(client, email="asha@example.com"):
    r = client.post("/borrowers", json={"full_name": "Asha Rao", "email": email})
    assert r.status_code == 201
    return r.json()["id"]


def loan_payload(borrower_id, **overrides):
    data = {"borrower_id": borrower_id, "principal_rupees": "100000",
            "annual_rate_pct": 12, "tenure_months": 12, "start_date": "2026-01-15"}
    data.update(overrides)
    return data


def test_create_borrower_and_reject_duplicate_email(client):
    make_borrower(client)
    r = client.post("/borrowers", json={"full_name": "Other", "email": "asha@example.com"})
    assert r.status_code == 409


def test_invalid_email_rejected(client):
    r = client.post("/borrowers", json={"full_name": "Asha", "email": "not-an-email"})
    assert r.status_code == 422


def test_create_loan_generates_full_schedule(client):
    bid = make_borrower(client)
    r = client.post("/loans", json=loan_payload(bid))
    assert r.status_code == 201
    loan = r.json()
    assert loan["principal_paise"] == 10_000_000

    schedule = client.get(f"/loans/{loan['id']}/schedule").json()
    assert len(schedule) == 12
    assert sum(i["principal_paise"] for i in schedule) == 10_000_000
    assert all(i["status"] == "PENDING" for i in schedule)
    assert schedule[0]["due_date"] == "2026-02-15"


def test_due_dates_clamp_to_month_end(client):
    bid = make_borrower(client)
    loan = client.post("/loans", json=loan_payload(bid, start_date="2026-01-31")).json()
    schedule = client.get(f"/loans/{loan['id']}/schedule").json()
    assert schedule[0]["due_date"] == "2026-02-28"
    assert schedule[1]["due_date"] == "2026-03-31"


def test_loan_for_unknown_borrower_is_404(client):
    r = client.post("/loans", json=loan_payload(999))
    assert r.status_code == 404


@pytest.mark.parametrize("bad", [
    {"principal_rupees": "500"},      # below minimum
    {"annual_rate_pct": -5},
    {"tenure_months": 0},
    {"start_date": "not-a-date"},
])
def test_invalid_loan_input_rejected(client, bad):
    bid = make_borrower(client)
    r = client.post("/loans", json=loan_payload(bid, **bad))
    assert r.status_code == 422


def test_missing_loan_is_404(client):
    assert client.get("/loans/12345").status_code == 404
    assert client.get("/loans/12345/schedule").status_code == 404
