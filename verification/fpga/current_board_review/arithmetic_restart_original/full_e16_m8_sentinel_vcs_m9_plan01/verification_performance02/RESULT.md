# Short Differential PASS; 600s Full-Scan Feasibility Not Established

Hilbert exact ENTRY review `PERFORMANCE_ENTRY02.json` SHA256 `0cd17c5bfee4fdac12987cf1cf5c106cb31e1710ea89b3c40738ff17a1c7be6b` accepted short tests only. ENTRY SHA256 `52609ab30082155678dea7f9f2937b922a264237f7f224306987ff17bbeb9f96`. All40 entry pins remained unchanged. No captured CSV/reference read, simulator, compilation, cProfile, budget change, sealed edit or retry occurred.

## Actual Exits And Timings

One child per interpreter, each fixed120s. Numeric waits were durably saved before subsequent validation:

| Interpreter | Actual wait | Child elapsed | Old consumer median | New consumer median | Old/new speedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python3.9.21 | 0 | 47.432769s | 2.226024s | 1.631375s | 1.3645x |
| Python3.11.13 | 0 | 42.373919s | 2.566915s | 1.712267s | 1.4991x |

These are unprofiled consume+partial-EOF timings over10994 constructed records, three old and three new samples per interpreter, alternating old/new/new/old/old/new. Each sample constructs a fresh Strict/observer outside its consumer timing. Setup was15.2451s on3.9 and12.0347s on3.11 and is explicitly excluded from the above medians. Child elapsed also includes constructed negatives, provenance checks and setup.

Individual old/new samples vary materially (3.9 old1.968-2.663s/new1.021-2.006s;3.11 old1.665-2.569s/new1.251-1.896s). Interpreters ran sequentially on a shared host, not under CPU isolation. No repeat was added to improve the apparent result.

Old3.9 -> new3.11 measured median speedup is only1.3000x. Old3.9/old3.11 is0.8672x: this experiment does NOT show a Python3.11 interpreter-only acceleration; new3.11 was also slower than new3.9 in these medians. Do not attribute the code optimization gain to the interpreter or claim Python3.11 inherently doubles performance.

## Exact Constructed Evidence

Both interpreters passed34 named differential/negative checks. Same existing fixture as the prior profile:10994 rows, four fully checked original calls, fifth helper entry; original4095 model remains available but no full4095 stream was generated. These earliest calls do not represent all target opcodes or later dictionary distributions.

Within each interpreter, old/new equality covered the COMPLETE Strict instance state (including regs, memory, fresh sets, call/read/helper ledgers), complete Prefix bookkeeping, complete generic/owner state excluding digest object identities, and complete partial result. Across interpreters, small result comparison confirmed identical fixture hash, all before/after digest values, row counts, entire owner/protocol summary and test names.

- Fixture SHA256: `39ac3652cf05e8af0b206485328f32f45cbfee133014fe1bb4b2c772fb3022f4`.
- All eight delivery digests (four per interpreter) equal `708be1303b1954adfd5c02524150576dad287edc0690b34b5e5487f04f1e2112`.
- Strict/observer/delivered rows10994 each; retired10813; CVX request/response47/47; architecture47; alloc/done20/20; required retired owners20; no pending tokens or unmatched suffixes. This constructed early scope proves the same necessary memory owners, not all full4095 target-owner coverage.
- Required-owner pair deletion, fresh init deletion, missing prior actual output read, first-row drop/duplicate/reorder, actual front/rear guard and LW-tail corruption all reject under both implementations.
- Each of14 fields mutated across yield rejects; missing/extra/reordered keys and non-string values reject. Size1 missing-byte and inherited size8 missing-byte checks reject rather than default. Existing bins retain Counter identity; new bins are independent.

## Runtime Decision

No evidence supports another full scan within600s. The old diagnostic stopped after111733676/296607084 bytes in595.5448s. A crude constant-byte-throughput full-file proxy is1580.93s, requiring2.635x reduction to reach600s. Dividing that proxy by the measured combined1.3000x gives1216.06s, still above600s.

That arithmetic is NOT a prediction or lower bound: startup cost, per-row CSV/framing/raw SHA cost, source phases, bytes/row, live contention and the fixture's limited target distribution differ. The new short timing does not measure parsing or raw hashing at all. Thus even a better short ratio could not guarantee600s; the measured ratio here is plainly insufficient to justify such a claim. No new raw scan is authorized or launched, and no budget extension is implied.

The three requested code changes remain isolated in this reviewed sidecar: one JSON serialization reused only after full tuple equality, missing-bin-only Counter construction, and direct checked size1 byte lookup. No other Strict semantic check was removed. Further optimization or another raw attempt requires a separate explicit decision; this task ends with measurements, not a scan.

## Actual Evidence Hashes

- `python39/result.json`: `69f87f33b4c6742996c60e48580170917f8cf29fec8103bcfeea2e6aa1ebeb18`.
- `python311/result.json`: `a7260d7365ed935d4f6fa3148d3de207316f60ac32c771b58276b92fc882bbfe`.
- `python39_actual_wait.json`: `5240092c415223496807061383a236241511adb4bf04a270315a736bf0170ca2`.
- `python311_actual_wait.json`: `bdac65cb398e48d28f400aae3a240a8df324d39909ebffad463344f55cce7cdc`.

Original timeout and failed diagnostic remain preserved; no architectural acceptance or scope closure is added.
