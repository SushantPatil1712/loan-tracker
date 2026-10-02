"""EMI and amortization schedule calculations.

Money is handled in integer paise. Interest is computed monthly on the
outstanding balance (reducing-balance method), the standard for most loans.
"""
from dataclasses import dataclass


@dataclass
class Installment:
    number: int
    emi: int          # total payment this month (paise)
    principal: int    # part that reduces the balance (paise)
    interest: int     # part that is interest (paise)
    balance: int      # outstanding balance after this payment (paise)


def calculate_emi(principal: int, annual_rate_pct: float, months: int) -> int:
    """Return the monthly EMI in paise.

    EMI = P * r * (1+r)^n / ((1+r)^n - 1), where r is the monthly rate.
    A 0% loan is just principal / months.
    """
    if principal <= 0 or months <= 0 or annual_rate_pct < 0:
        raise ValueError("principal and months must be positive; rate cannot be negative")

    if annual_rate_pct == 0:
        return round(principal / months)

    r = annual_rate_pct / 12 / 100
    factor = (1 + r) ** months
    return round(principal * r * factor / (factor - 1))


def build_schedule(principal: int, annual_rate_pct: float, months: int) -> list[Installment]:
    """Return the full month-by-month repayment schedule.

    Because EMI is rounded to whole paise, tiny errors would build up.
    The final installment is therefore adjusted so the balance ends at exactly 0.
    """
    emi = calculate_emi(principal, annual_rate_pct, months)
    r = annual_rate_pct / 12 / 100
    balance = principal
    schedule = []

    for n in range(1, months + 1):
        interest = round(balance * r)
        if n == months:                       # last installment clears the rest
            principal_part = balance
            payment = principal_part + interest
        else:
            principal_part = emi - interest
            payment = emi
        balance -= principal_part
        schedule.append(Installment(n, payment, principal_part, interest, balance))

    return schedule
