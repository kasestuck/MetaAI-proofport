# P8 failed real model candidate — regression input, never a repair

`mathutils.py` is a byte-for-byte copy of the first genuine Meta response's
candidate from P8. It is deliberately incorrect: 26/31 golden comparisons and
3/3 scoped tests passed. `provenance.json` binds its SHA-256 and source report.
Git may normalize line endings: the original raw byte hash and normalized UTF-8
LF hash are both recorded. The code content is unchanged.

Tests execute this code only inside Docker. It must not be used as a successful
translation, an offline fix, a model fallback or a replacement for new Meta
output. No corrected translation is supplied here.
