# Offline Checker Review Request, No Full Parse Authorized Yet

Both one-shot Spike processes completed with durable wait rc0 within the fixed
bound. Initial checker rejection was in startup, not the arithmetic oracle.
Original scripts, bound, ELFs and raw logs remain unchanged.

## Bounded Actual Prefix Evidence

`host.json` contains original six-line raw contexts and pre-write registers,
captured by reading only until the first affected store (hard20,000-line cap):

| Shape | Raw line | PC / instruction | Address | Width / value |
| --- | ---: | --- | --- | --- |
| e8/mf8 |1640|80000046 /0002b023|80002160|8 /0 |
| e32/mf2 |6248|80000046 /0002b023|800053a0|8 /0 |

Each address is that ELF's replay_log start. t0 equals the address, t1 the
actual __bss_end. Actual code is `sd zero,0(t0)` at `_start+0x46`, followed by
addi t0,8 and the original loop, before main. The first executor check assumed
all console-buffer writes were runtime bytes and rejected this legitimate
initialization. No time/file/step limit was hit. Actual child elapsed/raw:
e8 7.737235s/293505471B; e32 10.543294s/396412404B.

## Narrow Successor

`checker.py` keeps the original full oracle and adds `bss_guard.py`:
unique pinned startup PC/instruction; all BSS stores zero, aligned8, ordered
exactly from __bss_start through __bss_end; t0/t1/zero-register context; no
prior helper call, no reentry after main or printing. Entire BSS must have
been initialized before main. Console writes after main remain strictly
single-byte and in range. Original scalar/full-vector-result checks are not
relaxed. Ordinary unrelated scalar memory stores retain their old handling.

Host1 positive +11 negatives pass: nonzero clear, bad PC, out-of-range,
cross-console-end, misalignment, wrong t0/t1, prior calls, incomplete BSS,
runtime wide output and postprint reentry. `host.json` explicitly pins the
external `verification/coverage/scoped_rv64c_memory.py` decoder. The offline
executor includes that transitive helper plus sourceproof/models/ELFs and
all original input pins in its pre/post verification.

## Interrupted Earlier Attempt

Before the parent's new prior-review gate arrived, `offline02.py` was started
using a less precise startup-width successor. It was explicitly stopped on
that instruction (PID1551109, actual wait exit143). Its `input_pins.json` and
Host record remain; no full reference result or PASS was produced. This was
an interrupted partial read, not a new reference execution. It will not resume.
No original raw file changed. No claim is made that those bytes were never
read before; the admitted successor will perform one complete parse per raw.

`audit.py` is prepared but NOT executed. It requires explicit authorization
and the reviewed checker/Host hashes, writes fresh `fullparse01`, and has no
ELF execution, compile or retry path. Await parent review before using it.
