# Complete QK/PV Attention comparison

This successor keeps the accepted real Qwen3 input, full-call C timing,
strong rotating-register PV baseline, panel4 RVV QK baseline, and numerical
checks. Only the candidate arm substitutes resident QK and resident PV. It is
not a model benchmark or runtime-capability enablement.

The shape is D128, two query heads sharing one KV head, and 137 tokens in
64+64+9 tiles. A one-call smoke precedes the four-call ABBA measurement.
Preparation, query conversion, scale/mask/softmax, cross-tile rescaling,
normalization and final drain remain inside the measured complete call.
QK reads the same query rows already loaded by the SDK FULL command.

`qk_wrap.S` is deliberately limited to this caller's two heads and query base
zero. The reusable QK leaf is `software/akv/experimental/resident_attention/qk.S`.
The wrapper is not safe as a general override for a multi-group dispatcher;
runtime integration must pass the real query base explicitly and gate the
candidate on capability, shape, type and context admission.

The firmware builder verifies the old immutable software artifacts and copies
the sources it actually consumes. It does not revalidate the old hardware
acceptance against today's changed RTL, nor reinterpret an old failed run.
A fresh build is not RTL acceptance. Execution requires a separately accepted
Stage3 SoC image and the unchanged original PV boundary regression.
