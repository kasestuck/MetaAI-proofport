# Owned PHP 7.4 demo

Written for Proofport. Only run inside the Docker sandbox. No real secrets,
database, hostile payloads, uploads or network calls. The eight unsafe examples
are deliberately vulnerable patterns, not production recommendations. SQL uses
a string-returning connection double. Command cases use only harmless printf.
Tests/inputs are finite, not a security certificate. Offline patches are separate
source-hash-bound profiles; originals are never edited by the pipeline.
