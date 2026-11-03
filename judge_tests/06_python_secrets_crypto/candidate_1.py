import hashlib

# Controlled fake demo literal; not an actual password or service key.
DEMO_PASSWORD = None

def public_label():
    return DEMO_PASSWORD

def digest(value):
    return hashlib.md5(value.encode('utf-8')).hexdigest()
