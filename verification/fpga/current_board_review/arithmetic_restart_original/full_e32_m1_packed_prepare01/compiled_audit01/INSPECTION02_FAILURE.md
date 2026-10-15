# Static Inspector Operand Comment

`inspect02.py` returned numeric1 (tool chunkaaffdc), before RESULT.json.
Frame parsing encountered startup `addi sp,sp,-24 # ... <__stack_top>`.
That startup address formation is not a stack-frame allocation and includes
an objdump comment. Successor03 restricts frame collection to C routines
(number and later), and parses only the immediate token before comments.
Original scripts retained; only static inspection reruns, no Host/compile,
reference or DUT repetition. Both backend FP gate/store inspections had passed
up to the first backend's frame parser.
