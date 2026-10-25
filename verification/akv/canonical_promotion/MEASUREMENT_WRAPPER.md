# Prepared external-reader measurement wrapper

`akv_engine_synth_wrapper.sv` is a candidate replacement for
`verification/akv/synthesis/akv_engine_synth_wrapper.sv`, not a second production
engine. The existing file remains untouched. This candidate is separate from
`shared_resources.patch`; final packaging must include the reviewed interface
and source-list changes together.

All original top-level ports and package constants/types remain unchanged.
The candidate adds the shared-reader request/response typedefs, an actual
`qbs_akv_shared_reader`, and an AKV endpoint connection. Endpoint 0 is unused
and tied to an empty request; AKV uses endpoint 1. The wrapper records ownership
on actual command acceptance and retains it through success/fault terminal
handshake. All memory, MMU, physical-range and result ports remain connected to
real top-level signals. No test-only counter XMR or fixed functional response
is copied into the wrapper.

This is a single-client measurement boundary, not VLSU's production ownership
controller or gated-clock implementation. Reader counters are meaningful while
AKV owns the endpoint; they read zero when ownership is absent. They are not
persistent retired-command snapshots. Existing engine-unit compatibility
compositions deliberately handle that observation separately and are not this
measurement wrapper.

## Checks actually performed

- Five static tests check unchanged top ports and original package content,
  one reader, explicit endpoints, handshake-based ownership and real memory
  connections. These checks are not a functional proof.
- VCS compiled and elaborated `akv_engine_synth_wrapper` against the accepted
  snapshot03 source graph. Exit code was zero; the executable was produced.
  The exact inherited TLB genvar diagnostic was checked with the existing
  narrow admission; other IPDW/PCWM/PINMISSING and errors were rejected.
- All snapshot artifact hashes were checked afterward. Source, graph, log and
  executable identities are recorded in `wrapper-elaboration.json`.
- The first CLI attempt is preserved separately: `-Mdir csrc` was rejected
  because this VCS requires `-Mdir=csrc`. No RTL was changed to fix that error.

No simulation, DC synthesis, area, timing or power measurement was performed.
This generic-memory elaboration does not replace a macro-model packaging check.
Before enabling the old standalone DC flow, adapt its link-library and macro
hierarchy checks: the unified store uses one 64x256 Q macro and eight 128x256
KV macros, not the old two 96x256 legacy macros. Existing report classifiers
must not label the old organization as the new one. That physical-flow
qualification is not claimed by this preparation.
