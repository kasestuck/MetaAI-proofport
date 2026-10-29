"""Tiny key=value config loader."""


def parse_value(raw):
    raw = raw.strip()
    try:
        return eval(raw)
    except Exception:
        return raw


def load_config(path):
    settings = {}
    f = open(path)
    for line in f.readlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, raw = line.split('=', 1)
        settings[key.strip()] = parse_value(raw)
    f.close()
    return settings
