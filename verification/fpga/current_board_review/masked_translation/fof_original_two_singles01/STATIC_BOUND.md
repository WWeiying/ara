# Pre-Reference Bound

This bound precedes either Spike invocation. Software-only builds and Host tests
are complete; no reference or DUT result is inferred from them.

Exactly one final pinned Spike ELF per case is admitted, with the unchanged
limits: 1,500,000 simulator instructions, 120 seconds, 256 MiB raw file limit.
Actual wait status is persisted before parsing. Missing HTIF1, incomplete helper,
oracle, CSR restoration or any limit termination is NOT_ACCEPTED, never PASS.
No automatic retry, bound increase or source reduction is allowed.

## Compiled Successful-Path Upper Bound

Both actual disassemblies have finite counted loops and no polling loop before
the original exit. Only startup BSS clearing, page/output/mask initialization,
two complete state checks, ten trap-context fields and bounded printing repeat.
FOF itself executes once; no target fault handler, remap or retry is intended.

For a conservative count, charge the ENTIRE compiled `check_state` function
once per outer iteration, including every branch arm. Its callees are charged
separately at the entire `check` function length. This deliberately overcounts
the small output/guard/mask loops and avoids assuming a favorable branch path.

| Component | e8 | e64 |
| --- | ---: | ---: |
| Compiled check_state instructions | 141 | 121 |
| Compiled check instructions | 27 | 27 |
| check_state charged visits | 2*(2560+8+130+16+1)=5430 | 5430 |
| Total exact scalar check calls | 5477 | 5481 |
| BSS bytes, actual Spike ELF | 33224 | 34128 |
| Startup charge | (BSS/8+1)*5 | (BSS/8+1)*5 |
| Main initialization charge | (2560+8+4+130+16+10+5)*16 | same |
| Trap scaffolding charge | 21*109 | 21*110 |
| Other one-shot/printing/boot/exit allowance | 20000 | 20000 |

The 16-instruction initialization envelope exceeds all actual repeated main
bodies: page zeroing3, guard loop8, output loop6 and mask loop9 instructions;
the four original source writes and five post values are unrolled. The trap
charge covers both ten-field loops plus a whole function traversal; `check`
calls are already separately counted. Full main, handlers, transitions, original
11+3 instructions, bounded PASS printing and boot fit within the extra20000.
Post-HTIF parking is permitted only at the original jump PC and must terminate
inside the unchanged global instruction cap; it is not an oracle shortcut.

The generated `STATIC_BOUND.json` records exact sums below1.5M, final ELF/code
identities, Host result, and all executable checker inputs. The raw textual
size is independently bounded by RLIMIT_FSIZE; the expected successful trace
is much smaller than256 MiB, but a size-limit exit is still failure.

## DUT Planning Only

No DUT is admitted by this preparation. Related M2 H singles took294..332s for
about275k reference records; the M6 negative-stride single took996.680s with
836971 reference firmware records. At the slower273 retired/s proxy plus20%,
the compiled conservative bound below1.05M projects under77 minutes per case,
below3h, not a performance guarantee. Actual reference counts will refine the
planning estimate; future VCS budgets/admission belong to Main's later review.
