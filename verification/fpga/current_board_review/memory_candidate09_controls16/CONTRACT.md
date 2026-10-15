# M9 Controls16 Contract

Prepared plan SHA256: `cdd7cb977b22595b731cc3a4f12b92e4753cb5e134bf248d1dd77e4d7cd2f5fe`.

- Only the16 accepted control cases from memory_candidate08_recovery19/prepared01. No indexed/resident/recovery tasks selected.
- Same ELF bytes, original console/subcase oracle and mature artifact/trace checks. Direct M8 baseline CSVs, not a new M8 execution.
- Compare every CSV field across all310350 rows. Noncycle differences fail; retain every cycle difference in per-case cycle_differences.csv and summarize without falsely claiming equality.
- M9 image SHA25648d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a; same NrLanes4/VLEN1024/2MiB/Fpga0/AXI-delay/QBS+AKV/IDEALoff. No build, coverage or FSDB dump.
- Jobs1, unchanged180s per case, worker3300s, service3600s, cap24 and MemAvailable>=32GiB. No retry; stop first failure.
- Actual monitor numeric outcome persisted before generic/postchecks. Pins verified before and after; same source ELF checked before every dispatch.
- Direct unit ara-m9-controls16-01.service, KillMode control-group, Restart no, retained exit properties. Mature reviewed plan03 terminal publisher; candidate final record requires actual worker exit0 for acceptance.
- Focused Host5 actual0/1.449s; no baseline simulation or full-reference rerun. One dryrun before launch.
- Automatic complete.json contains full membership, performance_status, compared_rows, cycle_changed_rows, per-case comparisons and evidence hashes.
- Observe startup once, then no active simulation polling. Expected duration from prior16 is above10min; inspect after completion.
