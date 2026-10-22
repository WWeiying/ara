# M7 Same-ELF Controls16

Main authorized one sequential M7 run of the exact M6 normal controls. Actual
systemd launch returned0; unit ara-m7-controls16-01.service active/running,
direct worker1917160 and first M7 simv1917182 in its cgroup. First case is
smoke__rvv_vadd, seed1, exact private ELF, +NO_FSDB and private CSV. No software
compile, M6 write, DUT retry or additional control was introduced.

Plan SHA256: 10320629ffe1ef6220d4480278b666f05f0dd1d4ca9f68a162a8d7e37b606bd5
Image SHA256: e807e9243071ae078305ffa818f35c2902b33606fd20730fd6fe844a0924b7ba

The existing regression runner already accepts an explicit image; this narrow
successor additionally requires the exact M7 path/hash while retaining actual
snapshot, compiled manifest, configuration, image-payload and frozen-runner
checks. It derives only16 cases from the pinned M6 plan and binds their actual
accepted M6 CSVs, not the earlier M4 paths. ELF hashes/oracles are unchanged.

Each case retains180s; jobs1, summed case limits2880s, service hard cap3600s,
Restart=no, KillMode=control-group. Resource admission found2 external simv,
1 new slot and74005393408 available bytes. No original task was altered.

Host02 six tests passed (actual command exit0): exact scope/budgets, actual M7
identity, wrong M6 image rejection, exact/cycle-different/corrupt/truncated CSV,
console failures and resource cap. Host01 failure is retained: its tiny CSV
fixture lacked the order column. Only fixture/schema and report name changed;
the inherited comparison logic was not relaxed.

After each simulation exits, existing full generic CSV validation and exact
console oracle checks run; every row is compared against M6. The old total is
310350 rows. Noncycle differences reject; cycle-only differences are recorded
and explicitly marked REVIEW_CYCLE_DIFFERENCES, never called equivalence.
All16 includes qbs_control_smoke, akv_context_smoke, qbs_akv_handoff_smoke.
Sticky abort stops dispatch on first failure; final pins/metadata/evidence are
checked before complete.json publication. Startup is not terminal acceptance.

No active CSV content was read and no ongoing polling loop was started.
Service log: service.log; artifacts: prepared01/controls16/tests/.
