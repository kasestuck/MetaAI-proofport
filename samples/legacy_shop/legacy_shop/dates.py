"""Date helpers."""
import datetime

DATE_FORMAT = '%Y-%m-%d'


def parse_date(text):
    return datetime.datetime.strptime(text.strip(), DATE_FORMAT).date()


def days_between(a, b):
    return abs((parse_date(b) - parse_date(a)).days)


def sort_dates(items):
    """Sort a list of (date_string, label) pairs, oldest first."""
    items = list(items)
    items.sort(lambda x, y: cmp(parse_date(x[0]), parse_date(y[0])))
    return items


def age_label(days):
    if days < 7:
        return 'fresh'
    elif days < 30:
        return 'recent'
    return 'old'
