import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    """Return d moved forward by `months`, clamping to the end of shorter months.

    Example: 31 Jan + 1 month -> 28 Feb (or 29 in a leap year).
    """
    year_offset, month_index = divmod(d.month - 1 + months, 12)
    year = d.year + year_offset
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))
