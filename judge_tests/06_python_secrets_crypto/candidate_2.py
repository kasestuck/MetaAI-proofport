import hashlib

# Controlled fake demo literal; not an actual password or service key.
DEMO_PASSWORD = 'DEMO_NOT_A_REAL_CREDENTIAL'

def public_label():
    return DEMO_PASSWORD

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()
