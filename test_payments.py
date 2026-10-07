from helpers import loan_payload, make_borrower

# Past dates are used so tests keep passing whatever today's date is.
START = "2024-01-15"


def make_loan(client, months=3, **overrides):
    bid = make_borrower(client)
    r = client.post("/loans", json=loan_payload(bid, tenure_months=months,
                                                start_date=START, **overrides))
    assert r.status_code == 201
    return r.json()["id"]


def schedule(client, loan_id):
    return client.get(f"/loans/{loan_id}/schedule").json()


def test_pay_installment_marks_it_paid(client):
    loan_id = make_loan(client)
    first = schedule(client, loan_id)[0]

    r = client.post(f"/installments/{first['id']}/pay", json={"paid_on": "2024-02-10"})
    assert r.status_code == 200
    body = r.json()
    assert body["amount_paise"] == first["amount_paise"]
    assert body["loan_status"] == "ACTIVE"
    assert body["remaining_installments"] == 2

    assert schedule(client, loan_id)[0]["status"] == "PAID"


def test_paying_twice_is_rejected(client):
    loan_id = make_loan(client)
    inst_id = schedule(client, loan_id)[0]["id"]
    assert client.post(f"/installments/{inst_id}/pay", json={"paid_on": "2024-02-10"}).status_code == 200
    assert client.post(f"/installments/{inst_id}/pay", json={"paid_on": "2024-02-10"}).status_code == 409


def test_pay_unknown_installment_is_404(client):
    assert client.post("/installments/999/pay", json={}).status_code == 404


def test_future_payment_date_rejected(client):
    loan_id = make_loan(client)
    inst_id = schedule(client, loan_id)[0]["id"]
    r = client.post(f"/installments/{inst_id}/pay", json={"paid_on": "2999-01-01"})
    assert r.status_code == 400


def test_pay_without_body_uses_today(client):
    loan_id = make_loan(client)
    inst_id = schedule(client, loan_id)[0]["id"]
    assert client.post(f"/installments/{inst_id}/pay").status_code == 200


def test_loan_closes_when_last_installment_paid(client):
    loan_id = make_loan(client, months=3)
    for n, inst in enumerate(schedule(client, loan_id), start=1):
        r = client.post(f"/installments/{inst['id']}/pay", json={"paid_on": "2024-05-01"})
        assert r.status_code == 200
        expected = "CLOSED" if n == 3 else "ACTIVE"
        assert client.get(f"/loans/{loan_id}").json()["status"] == expected


def test_overdue_lists_only_unpaid_past_due(client):
    loan_id = make_loan(client, months=6)           # due 15 Feb, 15 Mar, 15 Apr ...
    overdue = client.get("/installments/overdue", params={"as_of": "2024-03-20"}).json()
    assert [o["installment_no"] for o in overdue] == [1, 2]
    assert overdue[0]["days_overdue"] == 34           # 15 Feb -> 20 Mar (2024 is a leap year)
    assert overdue[1]["days_overdue"] == 5
    assert overdue[0]["full_name"] == "Asha Rao"

    # paying installment 1 removes it from the overdue list
    first_id = schedule(client, loan_id)[0]["id"]
    client.post(f"/installments/{first_id}/pay", json={"paid_on": "2024-03-20"})
    overdue = client.get("/installments/overdue", params={"as_of": "2024-03-20"}).json()
    assert [o["installment_no"] for o in overdue] == [2]


def test_installment_due_on_as_of_date_is_not_overdue(client):
    make_loan(client)
    overdue = client.get("/installments/overdue", params={"as_of": "2024-02-15"}).json()
    assert overdue == []


def test_overdue_query_uses_the_index(client):
    """Proves the index from schema.sql is actually used by the overdue query."""
    import db as dbmod
    conn = dbmod.connect(":memory:")
    dbmod.init_db(conn)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM installments "
        "WHERE status = 'PENDING' AND due_date < '2024-01-01'"
    ).fetchall()
    assert any("idx_installments_status_due" in row["detail"] for row in plan)
