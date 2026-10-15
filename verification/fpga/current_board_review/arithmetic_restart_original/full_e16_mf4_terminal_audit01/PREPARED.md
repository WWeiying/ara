# Conditional E16 Terminal Auditor

Frozen, not started. Independent Averroes review is pending. Exact future
systemd command is in READY.json; do not launch a duplicate DUT.

- READY SHA256: c741ea5647461c3ee6dec714a1adc96ddb250b16a7f4157c71dd26ca9fe292b3
- pins.json SHA256: 7030cd815dafce22f28d2ad9ef84c86ca7b7ae535010236a5f95566ea1a6d8e4 (972 pins)
- terminal.py SHA256: ce6d46d2d780a4b7572df2a9d535488e89adf8f267f85badfd110a12109269a6
- Minimal observer Host8 passed; actual child wait0, 0.467415448s, PID1843553.
- No full source Host rerun, reference run, build, active CSV read or new DUT.

Narrow successor of full_e32_mf2_terminal_audit01/terminal.py, SHA256
7851a871f98589bf2bffd3fdb6388c14feb227c5473a8388c6ff92b5a7a5233e.
Only shape, approval/launch identities, exact worker PID and full-source totals
changed. AST equality checked for one_pass, HashLines, outcome_gate, wait_fd
and publish_success. Strict consumes the sealed e16 checker/profile/model.

The pidfd targets worker1842515 with exact argv and cgroup. After worker exit,
whole1 COMPLETE/PASS, numeric simulator exit0, no abort/retry and empty cgroup
are prerequisites to opening the sole CSV. A single lossless six-event parse
feeds both the frozen generic validator and full original Strict: 4095 calls,
65520 results, 8190 guards, 4095 vstarts, 53235 helper instructions. Source
order, full oracle, raw digest/identity, private ELF/image, pre/post pins and
actual offline child exit remain required. First failure is retained, no retry.

Wait14400s/offline900s/observer service15600s do not extend the simulator's
10800s hard limit, worker12000s or worker service13200s. Historical systemd
service exit is explicitly unconfirmed, never inferred from functional PASS.
