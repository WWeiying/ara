# Actual Authorized Startup

Executed the exact prepared02 ready argv, substituting only its three entry and
parent authorization placeholders. Actual systemd-run exit0; no retry, build,
source change or deadline extension. Parent admission SHAa280fb18... was checked
against the actual file before and after startup. Original worker resource and
PID/cgroup gates ran again inside the direct service.

- Unit: `ara-fp-unboxed-full17920-m9-01.service`.
- Main worker PID3568782; actual M9 simv PID3568853, same generation and private
  ELF/cwd/command confirmed.
- Actual manager: loaded/active/running, RemainAfterExit=no, Restart=no,
  KillMode=control-group, RuntimeMaxUSec=3h40min; ExecStopPost is the exact
  prepared02 `exit_hook02.py` command. Its not-yet-run placeholder fields are
  **not** interpreted as successful terminal status.
- Fresh preflight: total reserved/live-plus-this-job3, available177.977GiB.
- One3second positive-baseline observation: CPU ticks1816 ->2115;
  CSV bytes851968 ->1011712. No CSV rows were read.
- Fixed simulator/worker/service limits10800/12000/13200s, jobs1.

Evidence: `launch_command.json`, `systemd_run.json`, `preflight.json`,
`startup_discovery.json`, `startup_receipt.json`. Launcher process itself actually
returned0 (unified exec session50658, terminal chunk3a61ea).

Startup receipt SHA:
`4284f845cdb0e1ecccd259e7a46a436924b0f559bc0695d7d5f1e1240e50eda3`.
Actual command receipt SHA:
`f1358eef50907eaead835ff011d7e3406ef2410a471750e0fd3e6d828510be05`.

Observation is finished. No further active-job polling is scheduled by this
launcher. These receipts prove startup only. Architectural acceptance, actual
service exit and actual collector wait remain pending and must be read from
their real terminal records, not inferred from startup or process disappearance.
