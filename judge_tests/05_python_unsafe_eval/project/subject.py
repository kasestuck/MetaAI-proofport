def parse_value(value):
    try:
        return eval(value)
    except (ValueError, SyntaxError, NameError):
        return value
