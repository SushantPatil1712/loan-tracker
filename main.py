import sqlite3
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from dates import add_months
from db import get_db
from emi import build_schedule, calculate_emi

app = FastAPI(title="Loan Tracker API")


# ---------- Request models (validation happens here, before our code runs) ----------

class BorrowerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoanIn(BaseModel):
    borrower_id: int
    principal_rupees: Decimal = Field(ge=1000, le=100_000_000, decimal_places=2)
    annual_rate_pct: float = Field(ge=0, le=100)
    tenure_months: int = Field(ge=1, le=360)
    start_date: date


# ---------- Borrowers ----------

@app.post("/borrowers", status_code=201)
def create_borrower(borrower: BorrowerIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        cur = db.execute(
            "INSERT INTO borrowers (full_name, email) VALUES (?, ?)",
            (borrower.full_name, borrower.email),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A borrower with this email already exists")
    return {"id": cur.lastrowid, **borrower.model_dump()}


# ---------- Loans ----------

@app.post("/loans", status_code=201)
def create_loan(loan: LoanIn, db: sqlite3.Connection = Depends(get_db)):
    borrower = db.execute("SELECT 1 FROM borrowers WHERE id = ?", (loan.borrower_id,)).fetchone()
    if not borrower:
        raise HTTPException(404, "Borrower not found")

    principal = int(loan.principal_rupees * 100)          # rupees -> paise
    emi = calculate_emi(principal, loan.annual_rate_pct, loan.tenure_months)
    schedule = build_schedule(principal, loan.annual_rate_pct, loan.tenure_months)

    try:
        # Loan + all its installments are saved together or not at all.
        cur = db.execute(
            """INSERT INTO loans (borrower_id, principal_paise, annual_rate_pct,
                                  tenure_months, emi_paise, start_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (loan.borrower_id, principal, loan.annual_rate_pct,
             loan.tenure_months, emi, loan.start_date.isoformat()),
        )
        loan_id = cur.lastrowid
        db.executemany(
            """INSERT INTO installments (loan_id, installment_no, due_date,
                                         amount_paise, principal_paise, interest_paise)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (loan_id, i.number,
                 add_months(loan.start_date, i.number).isoformat(),
                 i.emi, i.principal, i.interest)
                for i in schedule
            ],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _get_loan_or_404(db, loan_id)


@app.get("/loans/{loan_id}")
def get_loan(loan_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _get_loan_or_404(db, loan_id)


@app.get("/loans/{loan_id}/schedule")
def get_schedule(loan_id: int, db: sqlite3.Connection = Depends(get_db)):
    _get_loan_or_404(db, loan_id)
    rows = db.execute(
        """SELECT id, installment_no, due_date, amount_paise,
                  principal_paise, interest_paise, status
           FROM installments WHERE loan_id = ? ORDER BY installment_no""",
        (loan_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_loan_or_404(db: sqlite3.Connection, loan_id: int) -> dict:
    row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Loan not found")
    return dict(row)


# ---------- Payments ----------

class PayIn(BaseModel):
    paid_on: date | None = None      # defaults to today


@app.post("/installments/{installment_id}/pay")
def pay_installment(
    installment_id: int,
    payment: PayIn | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    paid_on = (payment.paid_on if payment and payment.paid_on else date.today())
    if paid_on > date.today():
        raise HTTPException(400, "paid_on cannot be in the future")

    inst = db.execute(
        "SELECT id, loan_id, amount_paise FROM installments WHERE id = ?", (installment_id,)
    ).fetchone()
    if not inst:
        raise HTTPException(404, "Installment not found")

    try:
        # Only a PENDING installment can be marked PAID. Doing the check inside the
        # UPDATE itself means two simultaneous requests can't both succeed.
        updated = db.execute(
            "UPDATE installments SET status = 'PAID' WHERE id = ? AND status = 'PENDING'",
            (installment_id,),
        )
        if updated.rowcount == 0:
            raise HTTPException(409, "Installment is already paid")

        db.execute(
            "INSERT INTO payments (installment_id, paid_on, amount_paise) VALUES (?, ?, ?)",
            (installment_id, paid_on.isoformat(), inst["amount_paise"]),
        )

        remaining = db.execute(
            "SELECT COUNT(*) FROM installments WHERE loan_id = ? AND status = 'PENDING'",
            (inst["loan_id"],),
        ).fetchone()[0]
        if remaining == 0:
            db.execute("UPDATE loans SET status = 'CLOSED' WHERE id = ?", (inst["loan_id"],))

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "installment_id": installment_id,
        "loan_id": inst["loan_id"],
        "amount_paise": inst["amount_paise"],
        "paid_on": paid_on.isoformat(),
        "remaining_installments": remaining,
        "loan_status": "CLOSED" if remaining == 0 else "ACTIVE",
    }


# ---------- Overdue ----------

@app.get("/installments/overdue")
def overdue_installments(as_of: date | None = None, db: sqlite3.Connection = Depends(get_db)):
    """Unpaid installments whose due date is before `as_of` (default: today)."""
    as_of = as_of or date.today()
    rows = db.execute(
        """SELECT i.id AS installment_id, i.loan_id, i.installment_no, i.due_date,
                  i.amount_paise, b.full_name, b.email
           FROM installments i
           JOIN loans l     ON l.id = i.loan_id
           JOIN borrowers b ON b.id = l.borrower_id
           WHERE i.status = 'PENDING' AND i.due_date < ?
           ORDER BY i.due_date, i.id""",
        (as_of.isoformat(),),
    ).fetchall()

    result = []
    for r in rows:
        item = dict(r)
        item["days_overdue"] = (as_of - date.fromisoformat(r["due_date"])).days
        result.append(item)
    return result
