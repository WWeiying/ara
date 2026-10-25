#ifndef AKV_QUANTIZED_KV_FIELD_COPY_H
#define AKV_QUANTIZED_KV_FIELD_COPY_H

#include <string.h>

/* Fixed-size object-representation copies only. Explicit builtins allow GCC
 * and Clang to inline these even with -fno-builtin, without typed pointer
 * punning or stronger alignment assumptions. Keep bulk transfers separate. */
#if defined(__GNUC__) || defined(__clang__)
#define AKV_QUANT_FIELD_COPY(dst, src, bytes) __builtin_memcpy(dst, src, bytes)
#else
#define AKV_QUANT_FIELD_COPY(dst, src, bytes) memcpy(dst, src, bytes)
#endif

#endif
