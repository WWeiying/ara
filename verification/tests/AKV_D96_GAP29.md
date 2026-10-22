# AKV D96 Gap29: Precheck Ready, Not Launched

Selection: `verification/tests/akv_d96_gap29_selection.json`.
Aggregate handoff: `verification/tests/akv_d96_gap29_ready.json`.
ELF: `apps/bin/akv_d96_gap29`.

One V2 FULL, nine D96 row loads (three Q, three K, three V), one RELEASE.
Q rows=3, KV length=3, D=96, all strides=192 bytes. Descriptor alignment
is 64 bytes; each payload row is 32-byte aligned. Destination v8:v9 is
legal for D96, VL=96/e16/m2, and vstart is explicitly cleared before FULL.
All 864 active F16 bit patterns are distinct and finite. Each row is checked
against a scalar stream/row/dimension formula; 16-element guards precede and
follow each destination. No unspecified register-tail behavior is asserted.
Native asm declares v8/v9 and memory clobbers. Auto-vectorization is disabled.

Host mode uses the existing `software/akv/src/akv_v2_reference.c`, exercising
the same descriptor/stimulus against the scalar pattern oracle. It passed all
864 comparisons and destination guards. This is software-reference evidence,
NOT native custom-instruction execution or an RTL PASS. Stock Spike was not
used for these custom instructions. The SoC ELF passed the existing ELF-fit
checker for RAM 0x80000000..0x80200000. Runtime <=300s is a proposed bound,
not a measured result.

## Recipes

The completed build/precheck was:

```sh
cd /home/wangwy/openproject/ara_dsa_signoff_integration
python3 verification/tests/prepare_akv_d96_gap29.py
```

This intentionally refuses to replace its output directory or existing ELF.
Exact host and non-ZCC LLVM commands, working directories, dependency files,
logs, and RAM-fit results are frozen under:
`verification/out/akv-d96-gap29-precheck-20260928-01/`.
To rerun ONLY the software precheck without changing the pinned artifacts:

```sh
verification/out/akv-d96-gap29-precheck-20260928-01/akv_d96_gap29.host
```

## Coverage And Launch Policy

Source-level targets: V2 D96 descriptor acceptance, D96 row decode, and
six-word row replay including dimensions 64..95 for Q/K/V. These are candidate
targets, not proven unhit point IDs or measured coverage gains. Static review
confirmed D96 support in the archived original-image AKV package/engine and
dispatcher. V1 FULL is not legal for D96 and is not used.

Append only after the original-image 521-case batch completes AND the user
manually authorizes launch. Use only the original frozen image underlying
473 PASS, with its historical source provenance. Never substitute current
RTL or repaired-image VDBs. Ordinary FAIL/TIMEOUT evidence is retained and
the eventual campaign continues; only compatible PASS VDBs enter DVE.
No service, simulator, VCS compile, or coverage collection was launched here.
No existing test, tool, source pin, Makefrag, or RTL was changed.

The large preexisting QBS M8 case remains unselected: its runtime is unmeasured
and its comparator permits NaN. The temporary bounded M8 fallback was withdrawn
once this requested single D96 artifact passed precheck.
