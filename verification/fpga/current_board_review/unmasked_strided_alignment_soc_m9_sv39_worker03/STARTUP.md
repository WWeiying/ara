# Actual Sv39 Startup, Not PASS

- Service: `ara-strided-alignment-sv39-m9-03.service`.
- Direct worker MainPID **2718850**; actual simv PIDs **2718874**, **2718875**.
- One five-second pair of samples: CPU ticks **+508/+507**, CSV bytes
  **+323584/+356352**. Private ELF/trace argv and service cgroup matched.
- Actual observation: `startup_observation.json`, status
  `ACTUAL_SIMV_AND_CSV_PROGRESS_NOT_PASS`; observer actual exit0, tool `faef81`
  (completed exec session28394). No full CSV was parsed at startup.
- `systemd-run --user` actual exit0, tool `6062ce`.
- Actual preflight/resource/owner binding: `prepared01/launch.json`.
- Local appended stdout/stderr: `service.log`.
- Cases: `prepared01/sv39_2/tests/strided_alignment_load_sv39/` and
  `prepared01/sv39_2/tests/strided_alignment_store_sv39/`.
- Terminal when produced: `prepared01/complete.json`; any first error:
  `prepared01/firstfailure.json`.
- Concrete independent review:
  `../unmasked_strided_alignment_repair_zeno01/M9_SV39_WORKER_ENTRY03.json`, SHA
  `33be589731ac19f0c11d5203bf3522ffbe003c6c7ab878a5abf220e1bc0f912c`.
- Plan SHA `83a427884a035b7deda1923dd1000e6fc4043584306a15561f6c34fe8bc8d752`.

Only the two previously undispatched Sv39 cases run. M-mode closed results and
controls16 are accepted evidence reuse, not simulation jobs. Exact frozen M9,
unchanged ELF/source, strict endpoint02, complete original oracle and all owner
checks remain required. Jobs2, case900s, service4200s, no automatic retry.

This is a startup observation only. Background continues without further polling;
no aggregate or per-case DUT PASS is inferred here. No RTL or sealed predecessor
file was changed.
