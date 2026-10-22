# Preserved Host Failure

`runner_host01.log` and its numeric wait receipt retain 8 tests / 1 failure:
bare `FATAL` after a valid PASS was not caught by the imported common veto.
The successor runner explicitly adds the `FATAL` token; the negative test is
unchanged. This is a software acceptance-gate repair before any DUT launch,
not a DUT failure and not a relaxation of an architectural oracle.
