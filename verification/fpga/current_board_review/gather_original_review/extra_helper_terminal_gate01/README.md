# VI0 prefix112 terminal PC supplement

Prepared independent offline gate; **no DUT terminal audit has been run**.
This directory does not modify or replace the sealed worker, original PASS
markers, data oracle, helper, ELF or reference. No running CSV was used.

## Scope And Exact Source Policy

`audit.py` binds the original plan SHA
`bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11`
and original SoC ELF SHA
`a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74`.
It disassembles this ELF with the pinned objdump, not Spike's differently
linked ELF. All821 instruction boundaries/encodings cover the entire `.text`
and are checked against its actual ELF bytes. No pseudo-PC allowance exists.
The zero padding is inventoried but forbidden to retire. Trap handlers are
also forbidden even if a supplied retirement row has trap=0.

All20 helper bodies and capacity are matched to the pinned original
`operations.S`; the selected op2's13 encodings additionally match both
original-Linux and SoC instruction lists in the sealed source proof.
This is reuse/verification of that source proof, not a fresh whole-Linux-ELF
rebuild claim. Op20 is absent from this e8/m8 assembly; it is not fabricated
as another helper window.

- Selected op2 range `[0x800006fc,0x8000072c)`: all13 PCs must retire exactly
  112 times, in112 contiguous architectural-retirement windows. Non-retirement
  transport records can interleave; no integer/vector retirement can interrupt
  a helper window. Interior entry, duplicate/missing steps and113th call fail.
- Capacity range `[0x80000694,0x8000069c)`: its original3-instruction window
  must retire once, including exactly one capacity `vsetvli` at0x80000696.
- All other19 helper ranges: every instruction PC must have zero retirements,
  including scalar `mv` and `ret`, not just the entry or vector target.
- Every retirement PC/encoding must match an actual ELF instruction boundary.
  Other RVV/configuration/vector-CSR instructions are forbidden except the
  three precisely sourced initialization reads/writes below.
- CTRL success must be the original store with zero/full-byte-enable, after
  all112 calls; subsequent retirement can only be the original no-effect
  `0x80000076:a001` park. No Spike `0x8000007e` substitution is allowed.

### Three Required Source CSR Locations

Full static enumeration corrected the preliminary report's helper-only
1233 count. The actual source contains these additional one-time retirements:

| PC / code | Original source | Exact placement/check |
| --- | --- | --- |
| `0x8000002e:00805073` | prepared `startup.S:15`, `csrwi vstart,0` | Once, before wrapper/capacity/calls; rd0 |
| `0x80000082:c2202773` | SoC wrapper `main.c:5`, `csrr vlenb` | Once, after startup and before capacity; rd14=128 |
| `0x80000308:c22027f3` | prepared original-derived `case.c:52`, `csrr vlenb` for max_start | Once, after capacity and before first op2; rd15=128 |

No broad CSR exception is introduced. Repeated, missing, reordered or late
instances fail. With the frozen trace classifier, the expected architectural
vector/configuration/vector-CSR retirement count is
**112*11 +1 capacity +3 source CSRs =1236**. All13 helper instructions still
count112 each (the two non-CVX instructions are `mv` and `ret`).
This is not a1236 CVX-request ceiling: the existing generic validator's
narrow harmless CSR-read transport replay remains separate and unchanged.

## Single-Pass Terminal Use, Not Yet Authorized

Chosen implementation is the permitted **independent PC-only single pass**.
It does not rerun the old full data checker or filter rows before passing
them to another checker. It instead requires the original worker's completed
PASS and hash-bound `strict_prefix.json`/generic report for the same CSV,
including112 calls, all13 counts,114688 results,224 guards and112 vstart
checks. Existing raw logs, private ELF, command/provenance and original
report artifacts must still match the terminal's evidence pins.

The parent must supply the actual terminal path and independently observed
terminal SHA, then explicitly authorize this command. Do not run it while
the worker is active or before the parent authorizes the one complete audit:

```sh
python3 -B verification/fpga/current_board_review/gather_original_review/extra_helper_terminal_gate01/audit.py terminal \
  --authorize-terminal-once \
  --terminal /ABSOLUTE/ORIGINAL/OUTPUT/complete.json \
  --terminal-sha256 PARENT_VERIFIED_COMPLETE_SHA256 \
  --out verification/fpga/current_board_review/gather_original_review/extra_helper_terminal_gate01/terminal01
```

The output directory must be new. Terminal PASS/hash, original status,
membership, exit/budget and non-CSV evidence are checked before opening CSV.
CSV bytes are hashed while `csv.DictReader` traverses the entire file once;
no pre-hash or second full pass is performed. File identity/size/timestamps
must remain unchanged. The observed hash must equal both original terminal
and strict-report CSV hashes, and total rows/retirements/final cycle must
equal both original parsers. All helper PCs have explicit observed counts.

This supplement is not a replacement for data, input, marker, abort, resource
or protocol acceptance. Its CLI accepts a parent-verified original terminal,
not an arbitrary CSV alone. It does not query service/live state or reproduce
the full original pin scan over reference traces; the original terminal's
pin check remains required. It checks source-bound execution scope, not all
scalar branch/ALU semantics. A supplemental rejection is evidence to review,
not automatic attribution to an RTL bug.

## Host Evidence And Preserved Drafts

`test_host.py` only constructs small synthetic traces from the exact ELF
instructions. Their scalar data are not a replacement for the original
114912 data/guard checks. No old original worker Host suite, reference,
Spike, compiler or DUT is rerun.

The34 tests include exact112 positive, generic-protocol positive, streaming
CSV/hash agreement, and rejection of vi31 interior `0x8000074a:308fbc57`,
op0 interior vector/CSR/**integer**, duplicate or missing selected steps,
extra selected CSR/bootstrap CSR, missing/extra call/capacity, malformed
PC/code, trap/padding, bad exit, post-exit side effect and incomplete terminal.
The balanced synthetic extra-vi31 trace passes the frozen generic validator
(1237 vector-classified retirements) but fails the new PC supplement. This
is not a claim that the original VI0 full artifact gate was executed on that
synthetic trace. A transport-only harmless CSR replay positive is retained.

`inventory01/report.json` preserves a fail-closed draft caused by objdump's
default zero-padding omission. The fix is `-z` plus explicit padding rejection.
`inventory02/report.json` preserves the next fail-closed draft where the
initial allowlist included only wrapper vlenb, missing original startup
vstart and original-C max_start vlenb. All three locations were then established
from the exact original source and ELF, without inspecting DUT data.
`inventory03` is the first successful static inventory. Later inventory/Host
outputs retain final script identities; previous evidence is not overwritten.
`host01` is34/34 PASS before explicit per-helper-range report fields were added;
`host02/report.json` is the final **34/34 PASS**, zero failures/errors;
`inventory04` is the final821-PC/20-helper static inventory. No runtime
expectation was changed to match a DUT trace.

Final `audit.py` SHA256:
`bc92d1d2fb12f02fde729fc4d81b97d96b12d25602ad1ff6f0d94d6bc0f1528e`.
Final `test_host.py` SHA256:
`22476d8f8b0f965616db61e5b9d5e5d408397979a36bba2700cfe4b7d6682dc3`.
Readiness means the offline supplement is prepared and Host-tested only.
The one complete terminal CSV audit still requires parent authorization.
