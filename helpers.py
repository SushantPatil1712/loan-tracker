def make_borrower(client, email="asha@example.com"):
    r = client.post("/borrowers", json={"full_name": "Asha Rao", "email": email})
    assert r.status_code == 201
    return r.json()["id"]


def loan_payload(borrower_id, **overrides):
    data = {"borrower_id": borrower_id, "principal_rupees": "100000",
            "annual_rate_pct": 12, "tenure_months": 12, "start_date": "2026-01-15"}
    data.update(overrides)
    return data
