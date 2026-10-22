// Exercise the legal SEW/LMUL/policy cross with checked masked and tail lanes.

#include <stddef.h>
#include <stdint.h>

#include "vector_macros.h"

#define ELEMENTS 16
static const uint8_t mask_bits[2] __attribute__((aligned(128))) = {0x55, 0x15};

#define RUN_POLICY(SEW, EEW, LMUL, TYPE, SRC1, SRC2, DST, TAIL, MASK)          \
  do {                                                                          \
    TYPE lhs[ELEMENTS] __attribute__((aligned(128)));                           \
    TYPE rhs[ELEMENTS] __attribute__((aligned(128)));                           \
    TYPE initial[ELEMENTS] __attribute__((aligned(128)));                       \
    volatile TYPE observed[ELEMENTS] __attribute__((aligned(128)));             \
    size_t all_vl;                                                               \
    size_t avl = ELEMENTS;                                                       \
    asm volatile("vsetvli %0, %1, " #SEW ", " #LMUL ", tu, mu"               \
                 : "=r"(all_vl) : "r"(avl));                                    \
    if (all_vl < 2 || all_vl > ELEMENTS) {                                       \
      printf("unexpected VLMAX for " #SEW "/" #LMUL ": %d\n", (int)all_vl);   \
      ++num_failed;                                                              \
      goto done;                                                                 \
    }                                                                           \
    for (unsigned i = 0; i < ELEMENTS; ++i) {                                   \
      lhs[i] = (TYPE)(0x10 + i);                                                 \
      rhs[i] = (TYPE)(0x20 + i);                                                 \
      initial[i] = (TYPE)(0x80 + i);                                             \
      observed[i] = 0;                                                           \
    }                                                                           \
    for (unsigned pass = 0; pass < 2; ++pass) {                                 \
      size_t active = pass ? all_vl : all_vl - 1;                               \
      asm volatile(                                                               \
          "vsetvli zero, %[all], " #SEW ", " #LMUL ", tu, mu\n"               \
          "vlm.v v0, (%[mask_bits])\n"                                         \
          "vle" #EEW ".v " #SRC1 ", (%[lhs])\n"                              \
          "vle" #EEW ".v " #SRC2 ", (%[rhs])\n"                              \
          "vle" #EEW ".v " #DST ", (%[initial])\n"                          \
          "vsetvli zero, %[active], " #SEW ", " #LMUL ", " #TAIL ", " #MASK "\n" \
          "vadd.vv " #DST ", " #SRC1 ", " #SRC2 ", v0.t\n"                  \
          "vsetvli zero, %[all], " #SEW ", " #LMUL ", tu, mu\n"             \
          "vse" #EEW ".v " #DST ", (%[observed])\n"                        \
          "fence rw, rw\n"                                                       \
          :                                                                       \
          : [all] "r"(all_vl), [active] "r"(active), [mask_bits] "r"(mask_bits),  \
            [lhs] "r"(lhs), [rhs] "r"(rhs), [initial] "r"(initial),               \
            [observed] "r"(observed)                                             \
          : "memory");                                                          \
      for (unsigned i = 0; i < all_vl; ++i) {                                   \
        const unsigned selected = i < active &&                                 \
                                  ((mask_bits[i / 8] >> (i % 8)) & 1u);          \
        const unsigned undisturbed =                                             \
            (i >= active && #TAIL[1] == 'u') ||                                  \
            (i < active && !selected && #MASK[1] == 'u');                        \
        if (!selected && !undisturbed)                                           \
          continue;                                                              \
        const TYPE expected = selected ? (TYPE)(lhs[i] + rhs[i]) : initial[i];  \
        if (observed[i] != expected) {                                           \
          printf("policy mismatch " #SEW "/" #LMUL "/" #TAIL "/" #MASK       \
                 " pass=%d lane=%d got=%lx expected=%lx\n",                    \
                 (int)pass, (int)i, (unsigned long)observed[i],                  \
                 (unsigned long)expected);                                       \
          ++num_failed;                                                          \
          goto done;                                                             \
        }                                                                       \
      }                                                                         \
    }                                                                           \
  } while (0)

#define RUN_GROUP(SEW, EEW, TYPE, LMUL, SRC1, SRC2, DST)                        \
  do {                                                                          \
    RUN_POLICY(SEW, EEW, LMUL, TYPE, SRC1, SRC2, DST, tu, mu);                  \
    RUN_POLICY(SEW, EEW, LMUL, TYPE, SRC1, SRC2, DST, tu, ma);                  \
    RUN_POLICY(SEW, EEW, LMUL, TYPE, SRC1, SRC2, DST, ta, mu);                  \
    RUN_POLICY(SEW, EEW, LMUL, TYPE, SRC1, SRC2, DST, ta, ma);                  \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();
  RUN_GROUP(e8, 8, uint8_t, mf8, v1, v2, v3);
  RUN_GROUP(e8, 8, uint8_t, mf4, v1, v2, v3);
  RUN_GROUP(e8, 8, uint8_t, mf2, v1, v2, v3);
  RUN_GROUP(e8, 8, uint8_t, m1, v1, v2, v3);
  RUN_GROUP(e8, 8, uint8_t, m2, v2, v4, v6);
  RUN_GROUP(e8, 8, uint8_t, m4, v4, v8, v12);
  RUN_GROUP(e8, 8, uint8_t, m8, v8, v16, v24);
  RUN_GROUP(e16, 16, uint16_t, mf4, v1, v2, v3);
  RUN_GROUP(e16, 16, uint16_t, mf2, v1, v2, v3);
  RUN_GROUP(e16, 16, uint16_t, m1, v1, v2, v3);
  RUN_GROUP(e16, 16, uint16_t, m2, v2, v4, v6);
  RUN_GROUP(e16, 16, uint16_t, m4, v4, v8, v12);
  RUN_GROUP(e16, 16, uint16_t, m8, v8, v16, v24);
  RUN_GROUP(e32, 32, uint32_t, mf2, v1, v2, v3);
  RUN_GROUP(e32, 32, uint32_t, m1, v1, v2, v3);
  RUN_GROUP(e32, 32, uint32_t, m2, v2, v4, v6);
  RUN_GROUP(e32, 32, uint32_t, m4, v4, v8, v12);
  RUN_GROUP(e32, 32, uint32_t, m8, v8, v16, v24);
  RUN_GROUP(e64, 64, uint64_t, m1, v1, v2, v3);
  RUN_GROUP(e64, 64, uint64_t, m2, v2, v4, v6);
  RUN_GROUP(e64, 64, uint64_t, m4, v4, v8, v12);
  RUN_GROUP(e64, 64, uint64_t, m8, v8, v16, v24);
done:
  EXIT_CHECK();
}
