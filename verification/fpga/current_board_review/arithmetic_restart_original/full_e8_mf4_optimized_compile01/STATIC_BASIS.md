# One O2 Software Successor

No DUT launch is authorized by this preparation. The preserved -Os reference
completed all4095 calls in7,219,909 firmware instructions; its36,579,155 static
bound is not a runtime measurement. The -Os READY remains unchanged.

## Change and Falsifiable Cost Hypothesis

Only the RISC-V compiler flag -Os becomes -O2, as in the accepted
full_e64_m1_optimized_compile01 experiment. No source algorithm, initializer,
oracle, loop, original helper, runtime, linker script or model changes.
The original -Os ELF calls selected() at0x80000384,0x80000462,0x800004c2,
0x8000058a; selected contains remuw at0x80000086. O2 may inline predicate
selection and optimize its constant divisor, reducing scalar overhead.
This is a compiler-cost hypothesis, not an M9 performance measurement.
Both vectorization flags remain disabled. Every original helper encoding
must match the archived stripped Linux ELF; the reference rejects extra
vector instructions and checks every original scalar output read.

## C Semantics Before O2

For SEW8, word is uint8_t. Promoted add/sub operands lie in0..255, so their
int results fit; narrowing to uint8_t is defined modulo256. Multiplication
and logical shifts explicitly use uint64_t. Shift counts are0..7; RNG
shifts13/7/17 operate on uint64_t with defined modulo arithmetic. Signed
division checks zero and min/-1 first, with all e8 values within int64_t.
Reduction assignments narrow to uint8_t and cannot overflow signed int.

signed_word converts an out-of-int64-range unsigned representation to
int64_t; this is implementation-defined, not undefined. Right shift of
negative int64_t is also implementation-defined. The fixed GCC target uses
two's-complement conversion and arithmetic shift; unchanged compiler and
full independent numerical reference bind that behavior, not portable ISO C
across arbitrary compilers. Host UBSan complements, but does not replace,
this static review or the RISC-V reference.

Capacity is checked1..1024 before indexing. This shape returns32. The
physical a/b1024, out1026 and mask128 arrays remain intact. Index guards
protect slide/gather/compress reads; cap+1 is within out. uint8_t is the
unsigned-character type for these toolchains, so byte access does not
violate effective-type aliasing. No restrict, LTO or vector autogeneration
is added. External assembly calls remain opaque memory effects and use
caller-saved a/t registers, not callee-saved integer registers.

## Gates and Scope

Verify byte-identical C/main/runtime/assembly/header/model/Host rows against
the sealed -Os inputs, exact compiler arguments after path normalization
and the sole optimization substitution, and all26 original routines in
both backends. Host positive and8 negative checks remain full4095; a focused
UBSan Host pass checks the identical complete scalar path. One bounded
Spike run uses the unchanged40M steps/120s/6GiB ceiling and one full raw audit.
Full3seeds/25ops/4095calls/131040elements/8190guards/4095vstart checks remain.
No fflags oracle is invented where the original has none.

Budget from measured optimized retire count and mature actual DUT rates,
with20percent plus300s checking margin, not the static instruction ceiling.
Below10800s is only a plausible projection requiring independent entry
review, not permission here to launch DUT. No automatic additional flag
variant or budget increase. Original C is a byte-equivalent reconstruction
proved against the Linux ELF, not recovered original C bytes; the result is
full source-port history, not original Linux execution.

Pre-reference environment note: the dynamic UBSan link attempt failed because
/usr/lib64/libubsan.so.1.0.0 is absent. Its receipt/log remain untouched. The
focused Host check instead uses -fsanitize-undefined-trap-on-error, retaining
undefined-behavior instrumentation without a runtime library dependency.
No target ELF flag or source changes. O2 emitted failure.part.0; the reference
observer uses the already accepted e64 O2 failure/failure.* entry rejection,
with all other reference checks byte-identical to the e8 Os predecessor.
