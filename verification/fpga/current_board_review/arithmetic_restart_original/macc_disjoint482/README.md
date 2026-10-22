# Original Disjoint VMACC Prefix482

**READY: host and Spike reference PASS; no DUT launch.** Exactly one
`rvv_integer_macc_accumulators_restart_e8_m4` prefix, not the full22400-call
matrix, not other aliases/shapes, and not the separately running vadd prefix5.

## Review Entry

- [prepared02/status.json](prepared02/status.json): terminal preparation result.
- [prepared02/soc/programs.json](prepared02/soc/programs.json): existing SoC
  integration-runner input; SHA256
  `c41228e032836863c778fba60fb4246754e9b9b5c812a271ad323eaf8c165e5e`.
- [identity02/report.json](identity02/report.json): complete original Linux ELF
  byte-identity proof, without executing the complete program.
- [prepared02/historical_identity.json](prepared02/historical_identity.json):
  original stalled result and26 drained boundary prints.
- [prepared02/host/status.json](prepared02/host/status.json) and
  [prepared02/reference/status.json](prepared02/reference/status.json): actual
  validation results. [expected_inputs.json](prepared02/expected_inputs.json)
  records all482 exact enumeration positions and independent input/result hashes.

## Original Identity

Original ELF:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions42/binaries/rvv_integer_macc_accumulators_restart_e8_m4`.
SHA256 **`608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d`**.
The retained scene is `rvv_recovery08_14/terminal_scene/` under that campaign;
its ELF has the same hash. Assembly/header come from
`rvv_macc_restart_disjoint01/rvv_integer_macc_accumulators_restart_e8_m4.S`
and `operations.h`. The source manifest records five seeds, eight operations,
five accumulator patterns and22400 total configurations.

Using the original Buildroot GCC/flags and archived S/header, the **unchanged
current successor C** rebuilds the entire original ELF byte-for-byte. Its hash
is `ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006`;
the historical C hash is
`496a4ddbfa9a4b7c29e71287981d10860f76fcdd5c4bb55830e08bed8bd04222`.
Thus binary-equivalent source is established for this exact build; the old C
text bytes and old generator bytes are **not** claimed recovered. The complete
Linux ELF was compiled for identity only, not executed here.

## Exact Prefix and Oracle

Original loop order is seed -> opcode -> VL -> accumulator -> predicate ->
start -> rounding selector. This prefix runs seed0/op0 only, all80 calls for
each VL0/1/2/3/256/511, then the first two VL512 calls: **480+2=482**.
The last call is zero-based481, accumulator0, all-on predicate, VL512/start256,
rm0. Its pre-call trace exactly matches original `completed=481`. All26
printed boundaries in the retained failed scene match the independently
enumerated prefix and the successful Spike output. This links the software
sequence, not an internally captured original RTL handshake.

RNG, seed0 scalar-table assignment `b[0]=0`, all512 source elements, all128
predicate bytes, and all five accumulator patterns are preserved. Patterns
are zero, all-ones, sign-bit, alternating0x55/0xaa, and original per-element
arithmetic pattern. The independent host model snapshots old vd before
computing `(old_vd + a*b) mod256`. Oracle checks cover all512 elements per
call, both0x5b guards and returned vstart.

The original low32 returned-vstart check and high32 zero/saturation-container
check are retained exactly. This ordinary VMACC assembly returns only vstart;
it does **not** independently sample fflags/vxrm/vxsat. No new flags-coverage
claim is inferred from that high-word check.

The only bounding edit is an exit after the original scalar checks and
`++checks`, plus a label before the original summary. See
[prefix.diff](prepared02/prepared/macc_disjoint_e8_m4_prefix482/prefix.diff).
Runtime adaptation replaces Linux entry/write/exit and omits the tty-drain
service, retaining every original trace print. UART/OS drain timing is not
equivalent. The existing prefix5 startup/runtime/linker script are copied
byte-for-byte, not modified. No HINT, reset between target calls, filtering of
predecessor calls or replacement golden is introduced.

Target: `vmacc.vv v24,v8,v16,v0.t`, encoding `b5042c57`.
Original target/returned-vstart PCs: `0x108e0` / `0x108e4`.
SoC target: `0x8000087e`; Spike target: `0x80000876`.
Both ports retain all13 original op0 instruction encodings, including full
source/old-vd loads, MaskM load, vtype/vstart setup, target, CSR read and store.

The unchanged original summary says `seeds=5`, describing its full-matrix
setting; only seed0 executes here. Acceptance additionally requires exactly
`MACC_PREFIX_PASS macc_disjoint_e8_m4_prefix482 trials=482` and the exact
`cases=482 elements=246784 errors=0` original summary. All482 positions are
fully checked, including prestart, inactive and tail values with no agnostic
relaxation.

## Measured Validation and Cost

- Host2 positive runs PASS: bounded port and unbounded binary-equivalent
  original capture, stopping before computation of call482. Both match all482
  independently generated before/after FNV digests and exact call parameters.
- Host9 injected corruptions are rejected by the original scalar oracle:
  active, prestart, masked-off, tail, both guards, returned-vstart low word,
  return high word, and dropped accumulator contribution.
- Terminal checker6 tests PASS, including valid acceptance and rejection of
  contradictory PASS+FAIL, nonzero exit, wrong count, missing completion and trap.
- Nonzero-vstart Spike probe PASS. Reference ISA is exactly
  `rv64gcv_zvl1024b`. One482-call reference PASS, exit0, all26 historical prints
  matched, **16,438,522 retired instructions to replay_exit**, 2.579247s host
  reference time. This is not DUT cycle or wall-time evidence.
- A separate final read-only audit rechecked27 input pins,11 prepared files,
  both ELF hashes, exact source transformations, host hashes and reference
  markers. The sealed original vadd-prefix5 programs manifest remained
  `165c5c4d7dc83da93480b5389eda711aebd0af9928560f0aa5e0c0ea57e0da08`.

| Port | ELF SHA256 |
| --- | --- |
| SoC | `603f042e14179293da9351fc5610db32f5bd0a3d4f4984fb44d5cae8e5526b1b` |
| Spike | `0500bac3477b4a850b0f50170927dee982c43c0c78f31226d7d778b08349ff18` |

The instruction cost is about13.9 times the existing e8/m4 vadd56 reference,
so its short-prefix timeout must not be reused blindly. Applying the older
cross-suite1.223..1.330ms/instruction estimate gives roughly5.6..6.1 hours;
that is a conservative extrapolation, **not** a measured or approved VCS
budget. Parent should use the eventual current-prefix5 measurements before
authorizing a bounded run. No service, DUT runner, resource reservation or
image build was added in this task.

## Preserved Failures

`identity01` retains the first failed reconstruction. It incorrectly removed
the tty-drain return check and produced ELF hash
`bda33978692fc7f70f1adcdbc50050a5577ed02b39baf10a15d5e4650a904b07`.
Original disassembly proves the check at0x106be and contains
`RVV_TRACE_TTY_DRAIN_FAILED`; retaining the unchanged source in `identity02`
restored exact identity. No original arithmetic/oracle value was adjusted.

`prepared01` retains a checker-fixture failure after the positive/negative
data tests: case-insensitive `Error` matched valid `errors=0`. The successor
uses a whole-word generic ERROR/FATAL match and retains explicit
RVV_MATRIX_FAIL/FAILED, board failure/trap/mismatch and unsupported vetoes.
`prepared02` is fresh and accepted; earlier logs/failures remain unchanged.

Preparation can be reproduced only into a new owned output using
`prepare_prefix.py --out NEW_DIRECTORY`. Do not overwrite identity/prepared
artifacts or treat reference readiness as DUT or full-parent acceptance.
