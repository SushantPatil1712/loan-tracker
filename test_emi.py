import pytest
from emi import calculate_emi, build_schedule

RUPEE = 100  # paise per rupee


def test_known_emi_value():
    # Rs 10,00,000 at 10% for 12 months -> EMI is about Rs 87,916
    emi = calculate_emi(1_000_000 * RUPEE, 10, 12)
    assert abs(emi - 87_916 * RUPEE) < 1 * RUPEE


def test_zero_interest_loan():
    assert calculate_emi(120_000 * RUPEE, 0, 12) == 10_000 * RUPEE


def test_schedule_ends_at_zero_balance():
    schedule = build_schedule(500_000 * RUPEE, 9.5, 36)
    assert schedule[-1].balance == 0
    assert len(schedule) == 36


def test_principal_parts_sum_to_loan_amount():
    principal = 750_000 * RUPEE
    schedule = build_schedule(principal, 11.25, 24)
    assert sum(i.principal for i in schedule) == principal


def test_interest_decreases_over_time():
    schedule = build_schedule(300_000 * RUPEE, 12, 18)
    assert schedule[0].interest > schedule[-1].interest


@pytest.mark.parametrize("p,rate,m", [(0, 10, 12), (1000, -1, 12), (1000, 10, 0)])
def test_invalid_inputs_raise(p, rate, m):
    with pytest.raises(ValueError):
        calculate_emi(p, rate, m)
