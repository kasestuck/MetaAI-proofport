# legacy_shop

A deliberately old-fashioned inventory toolkit written for **Python 2.7**.
It exists as a realistic test subject for a legacy-code migration agent.

Contains typical Python 2 patterns: print statements, `except X, e`, `raise X, "msg"`,
integer division, `unicode`/`str` mixing, `has_key`, `iteritems`, `xrange`, long literals,
`__cmp__`, `cmp=` sorting, `raw_input`, and a few classic security smells
(`eval`, `pickle`, MD5 with a hard-coded key, SQL string building, `shell=True`).

Run with Python 2.7:

    python -m legacy_shop.cli sample_data/inventory.csv 2026-10-27
    python -m unittest discover tests

License: MIT. Original code, written for this project.
