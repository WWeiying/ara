# Actual E16 Startup

Authorized once; systemd-run returned 0. Before launch the unit was not-found,
MainPID 0, with neither launch.json nor replay/ present. All 959 plan pins and
ENTRY evidence pins were verified before launch. No sealed input was changed.

- Unit: ara-arithmetic-full-e16-mf4-m6-01.service
- Direct worker PID: 1842515; actual M6 simv PID: 1842618, same unit cgroup.
- Active/running; Restart=no; KillMode=control-group; service 13200s.
- Simulator limit 10800s, worker limit 12000s. No extension or retry.
- Plan SHA256: 17fc37e50f5420488a62872513fa77ce28ea89814ee2d5d3401ddcef27c751e0
- ENTRY: ../e16_mf4_entry_review01/ENTRY.json
- ENTRY SHA256: 962d5bc3dd83c88ff34c9c54fc747d6d37d4572fa330c83d00384846fe072fe2
- Corrected parent SHA256: d54061a36dfa826f08e9007ab3b3e88818476171a1a9847421f429251e8568bc
- Actual launch.json SHA256: bac85c5ee5f33bf4b04f81b0393598fb7a7da749af264b2b9aceec952d31c120
- Private input.elf SHA256: 509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6

Static source and actual ELF both emit BOARD_CASE_BEGIN rvv_matrix_e16_mf4;
the inherited console gate uses spec config id rvv_matrix_e16_mf4, not the
runner artifact name arithmetic_full_e16_mf4. Actual console confirms this BEGIN.
Actual simv argv uses frozen M6, exact private ELF, seed1, +NO_FSDB and private
commit_trace.csv; launch resource check reported 1 total slot and 87244406784
available bytes.

Bounded startup observation (100 CPU ticks/s): at Unix 1791863188.3269246,
user/system ticks were 2439/25 and CSV size 1449984 bytes; at
1791863190.3283362 ticks were 2637/26 and CSV size 1585152 bytes. This is
approximately 99.4% CPU and positive trace growth. Initial startup had no CSV
yet; no progress was claimed from that earlier sample. No active CSV content
was read, and no simulation polling loop was started.

Startup is not functional acceptance. Conditional full4095 terminal audit
requires whole1 PASS, actual numeric simulator exit0, no abort/retry, immutable
pins and one full lossless CSV traversal. Historical service exit is not inferred.
