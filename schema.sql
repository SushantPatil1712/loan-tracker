-- Loan Tracker schema (SQLite syntax; nearly identical in PostgreSQL)
-- All money is stored as INTEGER paise (1 rupee = 100 paise) to avoid float rounding errors.

PRAGMA foreign_keys = ON;

CREATE TABLE borrowers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE loans (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id      INTEGER NOT NULL REFERENCES borrowers(id),
    principal_paise  INTEGER NOT NULL CHECK (principal_paise > 0),
    annual_rate_pct  REAL    NOT NULL CHECK (annual_rate_pct >= 0),
    tenure_months    INTEGER NOT NULL CHECK (tenure_months > 0),
    emi_paise        INTEGER NOT NULL CHECK (emi_paise > 0),
    start_date       TEXT    NOT NULL,              -- ISO date: YYYY-MM-DD
    status           TEXT    NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE', 'CLOSED'))
);

-- One row per scheduled monthly installment, generated when the loan is created.
CREATE TABLE installments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id          INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    installment_no   INTEGER NOT NULL CHECK (installment_no > 0),
    due_date         TEXT    NOT NULL,
    amount_paise     INTEGER NOT NULL CHECK (amount_paise > 0),
    principal_paise  INTEGER NOT NULL CHECK (principal_paise >= 0),
    interest_paise   INTEGER NOT NULL CHECK (interest_paise >= 0),
    status           TEXT    NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING', 'PAID')),
    UNIQUE (loan_id, installment_no)
);

-- Payments are recorded separately so we keep a history of what was actually paid and when.
CREATE TABLE payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    installment_id  INTEGER NOT NULL REFERENCES installments(id),
    paid_on         TEXT    NOT NULL,
    amount_paise    INTEGER NOT NULL CHECK (amount_paise > 0)
);

-- Overdue lookups filter on status + due_date, so index them.
CREATE INDEX idx_installments_status_due ON installments(status, due_date);
CREATE INDEX idx_loans_borrower ON loans(borrower_id);
