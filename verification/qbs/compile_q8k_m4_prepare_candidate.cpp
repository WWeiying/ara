// Compile all VLA test caps with the target compiler before execution gates.
#include "ggml_q8k_m4_prepare_candidate.h"

template bool qbs_q8k_m4_prepare_candidate::quantize<1>(const float *, void *, int64_t);
template bool qbs_q8k_m4_prepare_candidate::quantize<7>(const float *, void *, int64_t);
template bool qbs_q8k_m4_prepare_candidate::quantize<16>(const float *, void *, int64_t);
