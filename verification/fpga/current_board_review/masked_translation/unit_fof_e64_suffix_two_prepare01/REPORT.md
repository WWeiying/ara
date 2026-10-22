# E64 Masked Suffix: Software Reference Handoff

Status: HOST14 + REFERENCE2 PASS; pending Tesla independent read-only review.
No DUT run, image build, production edit, or Linux closure is claimed.

## Authentic Scope

Archive root:
/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_exceptions01

| Single | Original ELF SHA256 | Original target | Selected helper |
|---|---|---|---|
| rvv_small_exceptions_e64_scenario1 | 25e13a67b7432e540269cca236a1b6596b66a0e152f121eb6f9ef8cc48ab0df4 | 0x10456 / 00057c07 | load_0, masked vle64.v |
| rvv_small_exceptions_e64_scenario2 | 5538ce81a3a80a64ac089efb9c5f6dba84fc7e1bc13dc7e36c8253eb8479e85e | 0x1047e / 01057c07 | load_1, masked vle64ff.v |

Each original single is round0 only, without predecessor vector calls.
source_proof.json verifies archived C/S/ELF hashes against manifest, measured
failure PC, canonical exception C with only the archived loop-limit selection,
and equality of all 11 instructions in BOTH load helpers plus the three capacity
instructions against the stripped original ELF. Both SoC and Spike ports pass
this comparison. The two archived assembly files are byte-identical.

Original C SHA256:
- scenario1: 7f331424b8561242b9fb1f0711061214f03b0ca68395ed2eec194a73fbec4646
- scenario2: 683457c8b49cf416525e86ad25e37dcfc45bd9acb869a5b61f4d39a2156a184e
- shared S: 79ac02eb05e4dcbb0788c8d65f912168c85416256f84309c82c63f2f5e958c04

The archived observed faults were load page fault / SIGSEGV at base+32, in the
masked-off suffix. New Sv39 programs are source-derived ports, NOT byte-identical
Linux ELFs. Linux mmap/mprotect/fork/wait/signal ABI is replaced by an S-mode
Sv39 mapping: readable first leaf and invalid second leaf. This reproduces the
protected-address architectural condition, not Linux's exact PTE encoding.

## Inputs And Oracle

- Original e64m1 tu/mu, VL8, vstart0; base page_end-32.
- Four initialized source words: 11, 48, 85, 122.
- All 130 output words initialized to typed uint64_t 91, not memset(0x5b).
- All 16 mask bytes initialized, byte0=15 and all remaining bytes=0.
- Original output: [11,48,85,122,91,91,91,91]; guards out[0],out[9]=91.
- Both helpers must return VL8/vstart0 BEFORE their original VL8 output store.
- No target exception, no remap/retry, no shortening, no undefined-suffix waiver.

The original eight-result/two-guard oracle is unchanged. Supplemental fixture
checks cover all 130 output words, all mask bytes, both 4KiB data pages, all three
page-table pages, physical page guards, trap context, and saved/restored CSRs.
Only the expected S-ecall after completed helper is allowed. fcsr=117 and
vcsr=5 are preserved; returned/trapped vtype=24, vl=8, vstart=0.

## Actual Reference

Each case has 172731 total commit records: 5 boot, 171023 firmware through HTIF,
and 1703 original inert parking records. This is below the authorized 800000
limit, INCLUDING boot/parking. Each checks 5481 scalar comparisons.

| Scenario | Spike actual child rc | Spike seconds | Parser plus post-pin seconds | Parser outer rc |
|---|---:|---:|---:|---:|
| 1 | 0 | 3.024203 | 6.251127 | 0 |
| 2 | 0 | 3.024840 | 6.328248 | 0 |

Numeric receipts: reference_scenarioN_01/execution.json and referenceN.wait.json.
The latter is an actual waited prepare/parser process, not an inferred child exit.
Raw hashes, exact target vector commit, target addresses, trap context, checkpoint
counts, and pin checks are retained in each status.json.

Each target executes once, with actual reads only at 0x40000fe0, 0x40000fe8,
0x40000ff0, 0x40000ff8. Full eight-element stores and all scalar checks pass.
Both checkpoints and all 11 selected helper retirements are checked in order.
All PCs/encodings must match the ELF; unused helper interiors and unrelated RVV
retirements are rejected. Parking is restricted to the original inert encoding.
No physical DUT request or internal handshake is inferred from these records.

Reference configuration: rv64gcv_zfh_zvfh_zvl1024b, --priv=msu,
--pmpregions=0, -m2, --instructions=800000; 120s wall and 256MiB raw-file limits.
Each reference ran exactly once; there are no failed/retried reference attempts.
The source-derived SoC BSS is 25928 bytes, Spike BSS 34128 bytes, within the
unchanged 1MiB runtime linker layout with 64KiB stack reserve.

## Backend Separation And Host Negatives

The corrected FOF startup observer and existing scalar RVFI checker were adapted
into NEW files only. Old sealed fixtures/checkers/results were not changed.

- Spike observer requires its Spike symbol table and HTIF value1.
- csv_check.Checker requires backend=soc and actual SoC symbols without tohost.
- SoC exit is the actual sd a0,0(t0), encoding 00a2b023 at 0x80000072,
  t0=0xd0000000, raw a0=0. The park is 0x80000076.
- Host14 uses both actual newly built SoC specs and an artificial scalar RVFI
  exit-store row. It accepts CTRL0 without a tohost symbol; rejects HTIF1,
  rc17, wrong source register value, byte enables/address, premature/duplicate
  exit and post-exit register side effects.
- Other negatives cover active/masked values, typed91 bytes, all guards, mask,
  page/PTE, returned VL/start, context, missing bytes, unused helper interiors,
  swapped target opcode, incomplete trace, and startup-completion confusion.

These are Host unit tests, NOT validation of a real DUT CSV or decoder port.
CSV checking must remain coupled to actual child numeric0, no abort/retry,
raw console failure veto, exact pass marker, full input/image pins and a
terminal worker receipt in the future replay. No replay worker is launched here.

## Frozen M9 And Entry

Image: /home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image
image.json SHA256:
48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a

M9_BINDING.json carries 610 inherited, independently rehashed frozen image/source
pins. Binding never substitutes current working-tree RTL for frozen M9.
Software commands and receipts are in build/host/reference*.wait.json.
No rerun is needed for review.

Future immutable replay inputs:
- software01/scenario1/soc.elf and soc.spec.json
- software01/scenario2/soc.elf and soc.spec.json
- csv_check.analyze(csv_path, decoded_soc_spec), plus the terminal gates above.

Full prep identities and reference result paths are in READY.json/input_pins.json.
At a conservative 273 records/s with 20% margin, 172731 records project to
759.3s per case, under 1h. This is an estimate, not measured M9 DUT timing.
Old M6 FOF fixtures of similar size took about 234-247s; they are not acceptance
or a guarantee for these new cases. No budget increase or oracle reduction
is authorized automatically.

## Falsifiable DUT Hypothesis

The first four active e64 elements fill one 32-byte lane word. The next word is
entirely inactive and maps to the protected page. A predicate-owner/window
transition defect could incorrectly translate element4; ordinary load would
trap, while FOF might silently shorten VL to4. Strict immediate VL8 and complete
masked-result checks distinguish both from correct skipping.

If a future measured failure requires capture, align target PC/VID with AddrGen
element_number, len, mask owner/first_element/valid, predicate valid/active,
descriptor push/pop/is_skip, MMU vaddr/request/exception, AXI AR handshakes,
VLDU issue/commit counters, mask_ready, VRF BE/final grant and same-VID done.
These are proposed probes, not observations. No RTL root cause is claimed yet.

## Independent Review Gate

Please relay this directory and READY SHA to Tesla for read-only source/Host/
Spike/checker/M9-pin review. Direct inter-agent messaging is unavailable here.
Independent review is PENDING, not claimed completed. Parent authorization and
a separately reviewed replay wrapper are still required before any DUT launch.
