# Actual Terminal Exit Observation

The independent event-capable collector was launched once as
ara-fof-original-two-m9-collector01.service, direct MainPID2822361.
Producer complete and exit-hook files had already closed before collector start;
the registered event waiter therefore returned immediately. No polling loop or
DUT/reference/CSV-semantic rerun occurred.

- Producer: real ExecStopPost exited/0/success, recorded1791970153.1274414.
- Collector: real ExecStopPost exited/0/success, recorded1791970191.7004416.
- Independent per-case metadata audit waits: numeric0 and0.
- e8/sc0 actual child0,260.542857501s;5477 original checks,161807 CSV rows.
- e64/sc5 actual child0,276.442952335s;5481 original checks,166262 CSV rows.
- Total10958 checks,328069 rows,eight nonempty source memory owners,830 unique
  verified pins. Original checker is in-process: no invented separate checker rc.
- No abort/retry/firstfailure. Full generic/strict reports and CSV byte hashes agree.

Result: PASS_INDEPENDENT_M9_FOF_ORIGINAL_TWO_TERMINAL_NOT_LINUX.
result.json SHA256:
07b2316d3351b980e98a46e4b21e41e52a53e62b4d6c824535b00098bf25b85e
Collector service_exit.json SHA256:
98239ca60f99ac731e1f9670d3d7fa20b801c1c9eaf1613d43b9b0b57fbdf6f4

The one post-launch service query saw LoadState=not-found after collection.
Its default MainPID0/Resultsuccess/ExecMainStatus0 are NOT exit evidence.
Acceptance uses the separately persisted actual systemd hook above.

Scope remains two source-derived Sv39 singles on frozen M9. e8/sc0 preserves
original undefined final output5..8 only, returnedVL4/start0; e64/sc5 retains
all eight outputs and VL8/start0. Neither Linux equivalence nor physical zero
MMU requests is claimed. The other eighteen cases were not rerun.
