# e8/m2 Full4095 Software Reference

Status: accepted complete software reference, NOT DUT and NOT Linux replay.
One reference and one fullraw parse; no retries, no RTL edits, no running-job
inspection. Existing sealed shapes and prior failures were not changed.

## Actual Outcomes

- Source gate: ../e8_m2_block_source_review01/SOURCE_ENTRY.json,
  NO_BLOCKER_HOST_COMPILE_ONLY, SHA256
  6cc07fb223a574eaa62c034fc7891bb04dab6ba685403d6ee140211327ac0923.
- Host/compile: `timeout 180s python3 -B prepare.py`, actual0,
  session51736/chunk1eb599.22 numeric Host receipts: original and packed each
  positive plus9 semantic negatives and1 expected UBSan trap. Every nontrap
  diagnostic/counter log matches between original and packed.
- Static inspector01 failed only on a copied universal ELF PC offset.
  STATIC_INSPECTION01_FAILURE.md and original script retained. Successor02
  actual0/session53789/chunk8bf5bd checks the actual separate instruction sites;
  no Host/compile rerun. Source helpers unchanged,328 original instructions,
  extra compiler RVV0, actual main frame304B.
- New observer/EOF20 tests: PID3211208, numeric0,1.069934s, no timeout.
- Exact reference entry: cf2a36507c1fb1e353cc98bfd619e359c525cb16b25af6cba876dd3ac3137f0c.
  Averroes final NO_BLOCKER JSON:
  ../e8_m2_block_source_review01/REFERENCE_ENTRY.json,
  SHA256 b4a22cb654c60dfafdadd2d723a05338c6ac61dc8b9f164cbb601c55a3613fb2.
- Invocation: `python3 -B reference.py execute --review
  ../e8_m2_block_source_review01/REFERENCE_ENTRY.json --review-sha
  b4a22cb654c60dfafdadd2d723a05338c6ac61dc8b9f164cbb601c55a3613fb2`.
  Wrapper actual0/session80413/chunk82ad30. Spike PID3213834 numeric0,
  4.478315s; auditor PID3213908 numeric0,54.802070s. Both no timeout/retry.
  ISA rv64gcv_zvl1024b; finite `rs 4000000` then `quit`,120s/768MiB;
  firmware cost acceptance3M. No backend options or budget were changed.

## Complete Scope

All3 original seeds/25ops/full4095 ordered calls remain. CAP256/m2/vtype1,
two complete128B physical registers, full256B input/old-destination/output,
full128B software mask initialization and actual32B vlm. Index255 is valid:
gather returns a[255], including targetVL3. No smaller CAP input reuse.

Actual reference verifies1048320 result bytes,8190guards,4095 returned-vstart0,
13 helper instruction positions each4095 (53235 total),135135 scalar output
reads (33/call),258 fresh output bytes/call,1575 complete mask initializations,
2208 original scalar input writes, capacity window exactly once.
Full EOF checked:5 boot+1069609 firmware+386 exact side-effect-free park
=1070000 raw rows. Original exact success console and HTIF1 verified.
No additional fflags or final CSR readback oracle is claimed.

Source C is binary-equivalent reconstruction, not recovered original bytes.
Original archived/rebuilt Linux ELF fe193c889801184a3144895f4817f0e9e6a9dfffae3144f6bf5bbcd311a1c0c6;
original S4e73c13c43d558cf7a4102590197abcd57db9a48e3cd15e373565207116f2237.
The scalar adaptation only changes exact initialization and positive oracle
representation; original byte failure fallback, helper bytes, RNG and history
remain. The dictionary has1260 blocks,121974B total ROM including indices/masks.
SoC ELF30eca586d305d0636c125c4ad4ebdf9acf267feb6163b6c460b75e3bb5d1354d:
text5244/rodata123472/BSS3272/stack gap916520B. Spike ELF
71b6f3e6ceabeddb37dd38782a23b2d0fe67e08eb313a9becdb49941afae3683:
stack gap908064B. Both exceed64KiB reserved stack within1MiB.

## Receipts And Limits

READY.json SHA256468fd4e35ef6cf66fe73f7f72ca88625054594eeb46d33d16cb20f652ce05627.
reference01/result.json SHA2569b08cbf1819e25f8356d4f04688192277229b8b6483dd424998b945975a018ae.
reference01/execution.json SHA25673d098450d94c28e70cd494a9ee417135b73ddb2c5b53c2af4c08c403b141ddc.
reference01/audit_execution.json SHA256be19e3ec5fca066980c72a60ac1a1f09c57c78bda5cb117db69ed0cd02c8d2f0.
Raw191653793B SHA2560cff38cae8858ff430a97bf083eb7bab506ce7a4a076abc70ec9e8270a6ffb42.
Pre/post pins unchanged. Immutable execution.validated=false is the numeric-
first receipt, not a later audit result; successful audit is separate.

At the inherited403.97 retired/s estimate plus20percent margin:3177.29s.
This is not measured DUT performance or authorization. No DUT worker or service
was prepared/launched. Future admission must independently bind actual ELF/
memory sites and model-derived ownership, including exact VI2/VL<=2 no-op and
nonempty op24 target. No generic slide exemption and no oracle reduction.
