# Frozen M9 Continuous1134 Entry

- Plan: prepared02/plan.json
- SHA256: dda443312e22010c1b68a0090032d15682049c554b1cc879f780444ca10ca51d
- Input pins:746. One full continuous program,1134 calls/366 exclusions;
  no partitions, restart, reference retry, software rebuild or RTL edits.
- Whole output oracle:1233792 byte checks/154224 word reads; fresh145152
  input stores and154224 output stores;2268 vstart reads;21366 original
  dynamically executed helper instructions.
- Required backend owners:4266 individually matched, comprising3402
  staging/readback and864 nonempty targets;270 empty targets may elide uops.
  Readback uses original vs1/2/4/8r, never assumed universally vs8r.
- Host02:12 tests PASS_HOST_ONLY, actual child0/143.756132s. This includes
  a real generic+strict single-pass synthetic full1134 stream and4266
  localized required-pair deletions. Worker02:5 tests including real SIGTERM
  children. Successor02:3 narrow schema/lifecycle equivalence checks;
  actual positive child0 and wrong-PC child1. Neither is DUT evidence.
- Prepare and dryrun02 both actually exited0. Dryrun emits one command only.
- Fixed budgets:case10800/worker12000/service RuntimeMax13200, jobs1.
  TimeoutStopSec360 reserves the metadata-only exit collector; no DUT budget
  extension. Reserved slots0 confirmed by parent; actual resource gate at run.
- Packed firmware reference4348773 instructions; conservative8397.635s
  cost projection is not measured M9 runtime.

Only Tesla's exact prepared02 entry may admit launch_once02.py. The original
prepared01 spec-serialization rejection and Host01 fixture failure remain
historical NOT_PASS/unlaunched records. All their sealed files remain intact.
