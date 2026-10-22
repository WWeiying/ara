# Remaining two original source singles on M9

Only e8/sc0 and e64/sc5 from the accepted fof_original_two_singles01 source port.
Exact same SoC ELFs; no compilation, new reference, or other eighteen DUT cases.

- e8/sc0: original VL8 active FOF crossing the protected page; returned VL4/start0.
  Only original final output indices5..8 are undefined, never guards or initial state.
- e64/sc5: alloff FOF on the protected page; VL8/start0 and all eight outputs strict.
- Original11 helper instructions, capacity3, full130-element allocation, mask16,
  two full8KiB data/12KiB page-table checkpoints, guards, CSR save/restore readbacks.
- Complete generic CSV plus inherited original checker and four nonempty memory owners.
  Exact hashbound main14 and completion-handler17 first opaque saves only, known GPR
  stores remain strict; all16 handler restores verify captured values/addresses/BE.
- Old M6 CSVs are read once for new-checker Host bridge, not treated as M9 evidence.
  Original M6 service-exit observation was unavailable and remains explicitly unknown.
- Two jobs,1800s per case,3900s worker,4200s systemd. No retry/build/FSDB.
  Direct MainPID, actual numeric child receipt before postcheck, failure veto,
  atomic abort-aware terminal, pinned systemd exit hook, fresh cap24/mem32GiB admission.
- Reference firmware169885/172547 records; M6 actual234.03/246.72s is a sizing proxy,
  not a guaranteed M9 runtime. Existing fixed1800s is unchanged.
- No Linux signal/history closure claim; zero physical MMU activity is not proved.
