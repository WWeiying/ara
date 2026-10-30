#include "q8k_m4_domain_vla.h"

template bool qbs_q8k_m4_domain_vla::check<1>(const float *, int64_t);
template bool qbs_q8k_m4_domain_vla::check<7>(const float *, int64_t);
template bool qbs_q8k_m4_domain_vla::check<16>(const float *, int64_t);
template bool qbs_q8k_m4_domain_vla::check<32>(const float *, int64_t);
template bool qbs_q8k_m4_domain_vla::check<64>(const float *, int64_t);
template bool qbs_q8k_m4_domain_vla::check<256>(const float *, int64_t);
