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
