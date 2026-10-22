# Static Inspector Failure

Original `inspect.py` returned numeric1 (tool chunk78cce2), before writing
RESULT.json: `ValueError: Original op>24 FP gate` at line59.
The target regex matched the preceding `,a5` register as hexadecimal0xa5,
not the final comma-separated branch destination. `inspect02.py` changes only
this extraction to the final operand. This is a static inspector defect, not
a Host, compile, reference, or DUT failure. Original script retained unchanged.
No Host or compiler is repeated; no reference or DUT is executed.
