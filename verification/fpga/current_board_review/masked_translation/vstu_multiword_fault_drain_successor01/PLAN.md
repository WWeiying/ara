# VSTU Drain Successor

Retain vstu_multiword_fault_liveness01/measurement01 unchanged.
Compile the exact previous private baseline dependencies, overriding only hardware/src/vlsu/vstu.sv
with the Main-notified candidate SHA. No VLDU compilation or global-root drift gate.

Seven separate original first-active fault cases: VL1/4/5/8/9/12/16; 4lanes/EW64/LMUL4/VSSE stride0.
Expected genuine mask windows:1/1/2/2/3/3/4. For every upstream handshake and local mask pop:
same instruction owner, ordered first-element0/4/8/12, below VL, no extra acceptance/pop.
Store done must not precede last mask pop; local spill A/B empty and st_idle true at terminal,
MASKU done once, commit/queue0, global idle true for cycles80..100.
External genuine packed mask and store-data lane beats only; no force/deposit/internal state writes.
First-active fault only: AW=W=B=0, pending_b=0; does NOT cover prior issued W or nonzero pending B.
100cycle result/200cycle watchdog/60s compile and per-case bound; once each/no retries.

Separate followups, never reuse first-active noW claims:
normal final W/maskpop same-cycle geometry; real prefix W with delayed B then fault drain;
new indexed idx0aligned AWaccepted/Wready0, idx1misaligned early_illegal, delayed W release then B.
Indexed baseline M6 first, then sole-VSTU candidate comparison. No RTL modifications by this worker.
