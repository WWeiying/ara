# Project Working Rules

## RTL debugging and performance investigation

- Do not debug by repeatedly changing RTL, parameters, timeouts, or software
  hints and rerunning simulations without a concrete hypothesis.
- First inspect the relevant RTL and software source, reconstruct the request,
  dependency, queue, execution, and completion paths, and verify the exact
  semantics of every counter or probe used as evidence.
- Form a falsifiable root-cause hypothesis before changing the design. State
  which cycle-level signals distinguish that hypothesis from the alternatives.
- Prefer one minimal, representative, and discriminating simulation over many
  trial runs. Use a bounded FSDB window and a focused signal profile when a
  cycle-level explanation is needed.
- Change RTL only after static analysis and measured evidence agree on the
  cause. After the focused test passes, run representative regression points
  to check correctness and performance impact.
- Do not poll simulations expected to run longer than ten minutes. Start them
  in an independent background directory, confirm that they are progressing,
  and inspect the result after completion.

## llama.cpp optimization integration

- Develop and measure an optimization first with a minimal benchmark using
  real llama.cpp model data. Do not tune only for synthetic inputs.
- When an optimization has reproducible benefit, stable numerical semantics,
  and applicability beyond one captured shape, integrate it into the
  llama.cpp/GGML RISC-V or Ara backend instead of leaving it only in the
  standalone benchmark.
- Backend integration must include runtime shape/type/capability selection and
  retain the standard RVV implementation as the fallback path.
- Keep benchmark and backend implementations derived from one kernel source or
  shared helper where practical, so performance experiments do not drift from
  the code used by real model execution.
