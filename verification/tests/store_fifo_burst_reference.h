// SPDX-License-Identifier: SHL-0.51
#ifndef STORE_FIFO_BURST_REFERENCE_H
#define STORE_FIFO_BURST_REFERENCE_H
#include <stdint.h>
#define SFB_CHECKS 2360u
#define SFB_SENTINEL UINT32_C(0xa5a5a5a5)
static const unsigned sfb_lengths[7] = {4, 8, 12, 16, 20, 28, 32};
static inline uint32_t sfb_source(unsigned word) {
  return word < 2 || word >= 34 ? SFB_SENTINEL :
    (UINT32_C(0x91e70031) ^ ((word - 2) * UINT32_C(0x01030507)));
}
static inline uint32_t sfb_expected(unsigned phase, unsigned word) {
  return word >= 2 && word < 2 + sfb_lengths[phase] ?
    sfb_source(word) : SFB_SENTINEL;
}
#endif
