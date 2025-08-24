from datetime import datetime, timedelta


def parse_date(date_value):
    if not date_value:
        return None

    if isinstance(date_value, datetime):
        return date_value.date()

    try:
        date_str = str(date_value).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
    except Exception:
        return None
