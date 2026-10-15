# M6 Bounded Wave Independent Review

Verdict: **CONFIRMED_WITH_EXPLICIT_BOUNDARIES**. No contradiction found in
Tesla's finalized bounded causal-chain evidence. This is not whole50 acceptance,
control acceptance, or proof of worker/service exit.

## Independent Checks

- `audit.py` independently parses both exported VCDs and the copied CSV. It
  does not import or execute Tesla's analyzer/finalizer. Offline execution rc0;
  output is `audit.json`. No DUT, recovery tool, RTL edit, or campaign poll.
- All 47 combined evidence pins match. The 13-file acquired raw family is
  unchanged in its private copies; recorded acquisition before/after/export
  inventories agree. The original writer-owned file later changed, as the
  source report explicitly records. No live file stability is assumed here.
- Vendor tool hashes match recorded identities. Recovery uses copied input
  and a new `recovered.fsdb` output, without `-cp` or `-del_src`. It merges the
  copied temporary files; neither command supplies replacement values.
  The recovered derivative is not claimed byte-identical to the original.
- Both VCDs have 100fs units. All 516 selected signal change blocks agree
  exactly. The 367700..369300ns export is within the recorded 1000000ns bound;
  10000000000 ticks equals 1000000ns. Clock period is 10000 ticks = 1ns.
- Rising-edge sampling uses stable values *before* that timestamp's changes.
  Every parsed edge satisfies wave time = monitor CSV cycle +15.5ns.
  `uop_alloc/uop_done` are real monitor events wired to sequencer
  `verify_vinsn_alloc/verify_vinsn_done`; completion is independently sampled.
  Delayed sequencer ready is not substituted for allocation acceptance.

## Measured Path

| CSV Cycle | Independent Observation |
| --- | --- |
| 368501 / 368516 | v4 source conversion EW32->EW64 allocation / completion |
| 368519 / 368536 | source snapshot allocation / completion |
| 368523..368533 | all four lanes x eight words actually captured after source completion |
| 368540 / 368555 | v4 destination conversion EW64->EW32 allocation / completion |
| 368557 | original VLXE allocation: vstart15, VL32, saved old EEW64, replay enabled |
| 368561 | saved word4 replay: lane values `[0x17000,0x4000,0x11000,0x1e000]`, queue-valid, live VRF-valid false, physical v4 tag EW32 |
| 368562 | actual AddrGen word and raw index `0x17000`, saved old EEW64; whole-word ready0, not a full-word dequeue |
| 368576 | actual MMU request `0x40017000` |
| 368588 / 368589 | MMU fault cause13/tval40017000; AddrGen fault vstart16 |
| 368718 / 368722 | retired CSR reads mtval40017000 / vstart16 |
| 369018 / 369154 | original address oracle succeeds / actual MRET |

All eight CSR fields match: mcause13, mepc80000d64, mtval40017000,
vstart16, VL32, vtype17, fcsr117, vcsr5. All nine handler check calls match.
Same original target encoding `0645f207` and same M5/M6 private ELF SHA:
`5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`.

Direct old M5 CSV inspection confirms architectural mtval
`0x400040017000` at cycle367806, PC8000061a, instruction34302973;
the original target has arch_start367643/order102 and accepted request367681.
The M6 target retains arch sequence102 and vstart15. Index16 from the authentic
formula is `((16*13+7)%32)*4096 = 0x17000`, hence VA40017000.

## Limits

The one original VLXE data-write handshake at cycle368588 has req&gnt=15,
addresses `[17,17,17,17]`, BE `[0,0,0,0xf0]`. Frozen four-lane EW32 shuffle
maps its enabled bytes to logical60..63: **element15 only**, not prestart0..14.
This is a data-write enable check, not independently measured equality of all
old-vd contents. Maintenance writes are separate. No complete old-vd/prestart
value-preservation assertion is made from this window.

At settled wave368512.5ns, mixed-layout=1, vstart15, v4=EW32/v5=EW64,
and surviving reshuffle_req_d=010 are observed. Earlier procedural assignments
inside the same always_comb are not independently sampled pre/post states.
`idx_op_cnt` is a remaining count, not an architectural element number.

Source report identities reviewed:
README `a5ab9d64f88d1884d790f2d5eeb4c89953a82ab01befcdbee4e3d81cd5244e6f`;
finding `70c3d8d2532e7093e668fd5c49e79f268766e02efab92c190cb5b80d42b1b233`.
Full input identities are retained in `audit.json`; no original or sealed input
was edited, and no simulation was launched or polled.
