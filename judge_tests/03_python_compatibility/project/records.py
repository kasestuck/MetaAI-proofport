def format_name(value):
    return value.strip().casefold()


def combine(left, right):
    return {'sum': left + right, 'label': format_name(' Demo ')}
