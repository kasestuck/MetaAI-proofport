import ast

def parse_value(value):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError, NameError):
        return value
