# Explicit migration fixtures, not AI outputs

`cases.json` is an authored input manifest, with no expected outputs. The harness
records outputs by executing the supplied originals in Docker Python 2.7.
Ninety cases cover functions, boundaries/errors, objects, CSV/config files,
sqlite/pickle, reports, and the CLI with explicit stdin. The ten existing tests
are also checked unchanged.

`patches.json` contains compatibility edits authored during this development
task and bound to each original module's text SHA-256. These are explicitly
labelled fixture candidates, never Meta responses or canned expected behavior.
They apply only to working copies. The original project is not edited or staged.

Finite examples do not prove arbitrary eval expressions, dict representations,
exact pickle interoperability or every input. The CSV diagnostic patch matches
the observed column order for this dataset. These limitations remain in reports.
No security fix is claimed by these compatibility patches.
