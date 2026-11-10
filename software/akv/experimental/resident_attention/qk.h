#ifndef AKV_EXPERIMENTAL_RESIDENT_QK_H
#define AKV_EXPERIMENTAL_RESIDENT_QK_H

#include "akv/akv_abi.h"
#include <stdint.h>

/* This helper does not query capability or establish context ownership. The
 * experimental caller must do both before calling the native instruction. */
extern void akv_experimental_resident_qk(float *scores, uint32_t tokens,
    uint32_t heads, uint32_t dimensions, uint32_t query_base);

static inline int akv_experimental_resident_qk_geometry(
    uint32_t tokens, uint32_t heads, uint32_t dimensions,
    uint32_t query_base, uint32_t loaded_queries) {
  uint64_t control = akv_resident_qk_control(tokens, heads, dimensions, query_base);
  return akv_resident_qk_command_is_valid(control, 0, 0) &&
      loaded_queries <= AKV_MAX_Q_ROWS && query_base + heads <= loaded_queries;
}

#endif
