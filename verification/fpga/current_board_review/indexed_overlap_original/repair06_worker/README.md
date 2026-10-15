# M6 Indexed Overlap Preparation

New successor of sealed `../vcs_candidate05_plan01/worker_successor.py`.
`checker.py` and `test_host.py` are byte-identical copies. No old output,
reference ELF, production RTL, or image is edited. No build or DUT is started
by host tests or the prepare command.

The new worker also serializes its deadline latch and final publication, checks
monotonic expiry after the pending-file write, joins the timer and refuses an
existing terminal file. Real-filesystem host negatives cover cancellation during
that write, delayed timer delivery, pending signal, and a stale post-commit timer.
The sealed M5 helper is not changed; checker/oracle semantics are unchanged.

Scope is the same three reference03 source-faithful Sv39 programs, each with
the complete original 50-round oracle. Fault cases require 1600 precise faults,
repair/SFENCE/MRET at the same target, all CSR/guard/backing memory checks;
resident retains the additional masked checkpoint. This is not original Linux
fault scheduling replay. Pilot fault_ov1 must pass before resident_ov1 and
fault_ov0 controls run at jobs2. No retries; sticky abort cancels peers.

Unchanged budgets: fault4200s, resident2400s, worker8800s, service9600s.
Resource cap24 and available memory32GiB remain the M5 shared gates.
The explicit unused reservation is additional to observed actual simvs.
The generated NOT_EXECUTED service command uses a direct worker, Restart=no,
KillMode=control-group and local append stdout/stderr. Generation is not launch.

Image must be exactly
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.
The existing shared gates verify compiled/source manifest, frozen snapshot,
all input/image hashes and the same configuration digest as M5/M4. Prepare pins
the actual M6 image; there is no fallback to M5 and no placeholder image SHA.
Execution checks the pinned image before and after the campaign and checks
each private ELF, inputs.json and actual command independently.

Capture retains the original 0..1000000ns window and adds dispatcher
indexed_mixed_vs2_layout, reshuffle_req_{q,d}, eew_{q,d}, eew_valid_{q,d},
and AddrGen original addrgen_operand_{i,valid_i,ready_o}. Frozen M6 signal-token
existence is checked at prepare/run. Host token checks alone do not establish
M6 runtime visibility or prove the RTL fix.

From this directory, host-only validation:

```sh
python3 -B test_successor.py --report host_successor_final.json
```

After M6 build finishes, prepare only (N is the parent's unused reservation):

```sh
python3 -B worker.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --unused-reserved-slots N
```

Preparation validates all three original ELF identities and helper encodings,
reference status/pins, real ELF ABI/maps, strict host tests and actual M6 image.
It writes a fresh plan and service_command.NOT_EXECUTED.json, never starts a unit.
Parent must review the exact plan/hash before any future authorized launch.
