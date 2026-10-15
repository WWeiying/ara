# Preparation Attempt01

The initial preparation process returned1 after all software builds, Host tests
and one successful Spike process had finished. Its offline checkpoint checker
rejected call1's mask because it constructed `bytes(255)`, meaning255 zero
bytes, instead of the intended single byte255. This is a Python fixture
parser error, not a change to the C oracle or a reference/DUT numerical failure.

`prepare_attempt01.py` preserves the complete original script. The initial
failure was `ValueError: call1 loaded predicate`, at original line225.
`prepared01/host.json` and the original Spike command/log/ELFs remain untouched.
The log ends with exact original `RVV_FP_COMPARE_PASS sew=16 cases=50 errors=0`,
case/runtime PASS and firmware exit0. The checked subprocess helper returned
normally before the parser failure; the outer preparation process did not PASS.

The successor fixes only this byte constructor in the checkpoint predicate
check and adds an offline-finalization entry. No C, assembly, ELF, debugger
commands, Host results, or original raw log is replaced. No Spike rerun.
Initial Spike wall elapsed was not persisted before the parser failure and
will remain null, not an invented timing. Instruction cost remains available
from the actual start/exit minstret checkpoints.
