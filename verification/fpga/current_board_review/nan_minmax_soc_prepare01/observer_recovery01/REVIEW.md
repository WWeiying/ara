# Observer Recovery Entry

Status: successor Host passed; independent entry review pending. This is not
raw architectural reference acceptance or DUT acceptance. Original STOPPED,
checker, reference runner and reference01 remain unchanged. No second full
raw parse, Spike redispatch, VCS, image build, or RTL edit occurred.

## Actual First Attempt

call1294 Spike child exit0, no timeout, elapsed2.974907114636153s.
Raw commits.log120823576B, SHA
e34f4499c3ad85517edf41eb4da8ba436ba6026ce18f48e33358827f32e161e1.
actual_exit_unvalidated.json SHA
afb62cf97fddb2cc88c86dbc850315e5646a55fc0cc051dcf32ca9e66da4ce30.
execution.json SHA
587d141cd96ffa0a31165eb8ac9d8b51be5d3baf37115dcc185ec41b37663016.
The numeric receipt was saved before metadata hashes/parser/checker work.
call1234 has an admission but was not dispatched after first error.
Original first cause: raw bitwise result/flags/vstart.
No READY or full reference PASS has been produced.

## Observed State Chain

The following values were read from the original raw matching helper PCs:

| PC | Instruction | Actual effect |
| --- | --- | --- |
| 800007f2 | 00202ef3 / csrr frm | x29=0, saved context |
| 800007f6 | 00102f73 / csrr fflags | x30=0, saved context |
| 800007fa | 00281073 / csrw frm,a6 | c2_frm=0 |
| 800007fe | 00189073 / csrw fflags,a7 | c1_fflags=0 |
| 80000802 | 1c881c57 / vfredmax.vs | v24 low32=7fc00000, remaining124B=5b; c8_vstart=0; no fflags delta |
| 80000806 | 00802573 / csrr vstart | x10=0 |
| 8000080a | 00102373 / csrr fflags | x6=0 |
| 80000814 | 002e9073 / restore frm | c2_frm=0 |
| 80000818 | 001f1073 / restore fflags | c1_fflags=0 |

Expected independent bits/fixture:7fc00000,flags0,vstart0. Full destination
expected4B canonical NaN plus124B5b. Source op2 uses e32/m1,tu,mu throughout;
cap32 full source load, mask load4B=24242424, requestedVL3. Only source
element2 participates. Reduction updates destination element0 and preserves
the full old destination tail. The original output oracle checks all144B,
including both8B guards; this oracle has not changed.

Root cause is the observer's mandatory row.csrs.get('fflags')==0 comparison
on a per-instruction write delta. Spike decode_macros.h214 performs an
fflags write only when raised flags are nonzero. Explicit fsflags0 logs the
write, but qNaN/qNaN maximum raises no flags and emits no fflags delta.
The result bytes, vstart and later actual fflags read are correct in the
matched records. This establishes the observer diagnosis, not a substitute
for complete offline raw acceptance.

## Successor Gate

checker.py preserves raw CSR delta dictionaries. Missing reduction fflags
is carried only from an explicit adjacent source-PC/code-bound fsflags0,
whose actual operand and logged value are both zero. Full21 helper CSR
tracking rejects unknown/unexpected CSR effects; fcsr aliases must agree
with known frm/fflags. Actual index13 read must match the tracked state.
Original PC/encoding/setup/data/mask/fixture/full128B store/full144B oracle/
flags/vstart/context/terminal checks remain.

host02.json per scope: explicit-delta and unchanged-omission ledger positives,
one parsed raw omission positive,15 state negatives,33 baseline ledger
negatives and one parsed raw NV-insertion negative. The raw Host witness is
synthetic and labeled Host-only, not a fabricated architectural record.
The NV mutation inserts c1_fflags even when the original line omits it.
No default unknown-state-to-zero or edited old oracle is used.

checker.py SHA783ca239cc93e90dc6579f75ed7f6cc92cd59bce9a1820dbf31ddd08d40f9958.
test_host.py SHA886e4da5e11354193691a57250c49f7c3dc0beece14bf103bed08ae36cc557a9.
raw_mutations.py SHA49329c84bff150205f08472a3b06e09a4576b0fd27405435abc90e40f33c054d.
host02.json SHA0956086ea83ac2562f8533f4b47f3e94d8d2879f3d1bc883a54305af2d1a3832.

Aquinas was notified for independent entry review. Complete offline parsing
of unchanged reference01, remaining actual-raw mutation tests and independent
acceptance remain pending. No further dispatch is authorized by this report.
