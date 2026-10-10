// SPDX-License-Identifier: SHL-0.51
// Directed FP16 -> I8/U8 narrowing; no scalar floating-point reference.
// Requires V + Zvfh. Build with the normal scalar (vec=0) test flags.
#include "vector_macros.h"

// The default retains the original full 384-case suite at VLEN >= 1024.
// Shards opt into 80 additional boundary cases; IDs are zero-based ordinals.
#ifndef VFNCVT_INT8_SHARD_COUNT
#define VFNCVT_INT8_SHARD_COUNT 1
#endif
#ifndef VFNCVT_INT8_SHARD_ID
#define VFNCVT_INT8_SHARD_ID 0
#endif
#ifndef VFNCVT_INT8_EXTRA_BOUNDARIES
#define VFNCVT_INT8_EXTRA_BOUNDARIES 0
#endif
#ifndef VFNCVT_INT8_SMOKE
#define VFNCVT_INT8_SMOKE 0
#endif
#if VFNCVT_INT8_SHARD_COUNT < 1 || VFNCVT_INT8_SHARD_ID < 0 || \
    VFNCVT_INT8_SHARD_ID >= VFNCVT_INT8_SHARD_COUNT
#error Invalid vfncvt_int8 shard selection
#endif
#if VFNCVT_INT8_SMOKE && (VFNCVT_INT8_SHARD_COUNT != 1 || !VFNCVT_INT8_EXTRA_BOUNDARIES)
#error Smoke requires one shard and extra boundaries
#endif

enum { NX = 1, DZ = 8, NV = 16, CAP = 8192 };
enum { RNE, RTZ, RDN, RUP, RMM };
enum { MIXED, EXACT, FRACTION, INVALID };
static uint16_t src[CAP] __attribute__((aligned(128)));
static uint8_t initial[CAP] __attribute__((aligned(128)));
static uint8_t result[CAP] __attribute__((aligned(128)));
static uint8_t mask[CAP / 8] __attribute__((aligned(128)));
static unsigned cases, ordinal, byte_checks, active_checks, csr_checks;
static uint64_t selected_ids[16];

// Call before prepare(), input generation, or reference work. Emitting the
// selected-ID bitmap lets the bundle validator prove disjoint, complete union.
static int selected(void) {
  unsigned id = ordinal++;
#if VFNCVT_INT8_SMOKE
  int take = (id < 240 && id % 12 == 0) ||
             (id >= 288 && id <= 306 && (id - 288) % 6 == 0) ||
             (id >= 384 && ((id - 384) % 20) / 4 == RTZ);
#else
  int take = id % VFNCVT_INT8_SHARD_COUNT == VFNCVT_INT8_SHARD_ID;
#endif
  if (take)
    selected_ids[id / 64] |= UINT64_C(1) << (id % 64);
  return take;
}

// Zeros, signed subnormals/min-normal, ties and neighbors, signed/unsigned
// limits, largest finite, infinities, and both signs of quiet/signaling NaNs.
static const uint16_t mixed[] = {
    0x0000, 0x8000, 0x0001, 0x8001, 0x03ff, 0x83ff, 0x0400, 0x8400,
    0x37ff, 0x3800, 0x3801, 0xb7ff, 0xb800, 0xb801, 0x3e00, 0xbe00,
    0x4100, 0xc100, 0x4300, 0xc300, 0x3d00, 0xbd00, 0x3f00, 0xbf00,
    0x57e0, 0x57f8, 0x57e8, 0x57ef, 0x57f0, 0x57ff, 0x5800, 0x5801,
    0xd7ff, 0xd800, 0xd801, 0xd804, 0xd807, 0xd808, 0xd810, 0xdc00,
    0x5bf8, 0x5bf9, 0x5bfb, 0x5bfc, 0x5bff, 0x5c00, 0x5c01, 0x6400,
    0x7bff, 0xfbff, 0x7c00, 0xfc00, 0x7e00, 0xfe00, 0x7c01, 0xfc01,
    0x3c00, 0xbc00, 0x4000, 0xc000, 0x5400, 0xd400, 0x5bf0, 0x3555};
static const uint16_t exact[] = {
    0x0000, 0x8000, 0x3c00, 0x4000, 0x4200, 0x4400, 0x5400, 0x57f0};
static const uint16_t fractions[] = {
    0x0001, 0x03ff, 0x0400, 0x3555, 0x37ff, 0x3800, 0x3801, 0x3d00,
    0x3e00, 0x3f00, 0x4100, 0x4300, 0x4700, 0x4b40, 0x53f8, 0x57e8};
static const uint16_t invalid[] = {
    0x7c00, 0xfc00, 0x7e00, 0xfe00, 0x7c01, 0xfc01, 0x7bff, 0xfbff,
    0x5c01, 0xdc01, 0x6400, 0xe400, 0x6401, 0xe401, 0x7bfe, 0xfbfe};
// Single-element cases prevent another lane's NV/NX from hiding bad flags.
static const uint16_t boundaries[] = {
    0xb800, 0xb801, 0x57f8, 0x57ff, 0xd804, 0xd807, 0x5bfc, 0x5bff};

static uint8_t reference(uint16_t h, unsigned uns, unsigned rm,
                         unsigned *flags) {
  unsigned sign = h >> 15, exp = (h >> 10) & 31, frac = h & 1023;
  unsigned limit = uns ? 255 : 127;
  if (exp == 31) {
    *flags |= NV;
    return frac || !sign ? limit : (uns ? 0 : 128);
  }
  // Finite magnitude = significand * 2^(exp-25), subnormal frac * 2^-24.
  unsigned sig = exp ? 1024 + frac : frac;
  int shift = exp ? (int)exp - 25 : -24;
  unsigned mag, rem = 0, half = 0;
  if (shift >= 0) {
    mag = sig << shift;
  } else {
    unsigned bits = -shift;
    mag = sig >> bits;
    rem = sig & ((1u << bits) - 1);
    half = 1u << (bits - 1);
  }
  if (rem && ((rm == RNE && (rem > half || (rem == half && (mag & 1)))) ||
              (rm == RMM && rem >= half) || (rm == RDN && sign) ||
              (rm == RUP && !sign)))
    ++mag;
  // Range is checked AFTER rounding. Invalid suppresses this element's NX;
  // a different valid, inexact element can still contribute NX to the CSR.
  if ((sign && mag > (uns ? 0u : 128u)) || (!sign && mag > limit)) {
    *flags |= NV;
    return sign ? (uns ? 0 : 128) : limit;
  }
  if (rem)
    *flags |= NX;
  return (uint8_t)(sign ? -(int)mag : (int)mag);
}

static uint16_t sample(unsigned kind, unsigned i) {
  switch (kind) {
  case EXACT: return exact[i % 8];
  case FRACTION: return fractions[i % 16];
  case INVALID: return invalid[i % 16];
  default: return mixed[i % 64];
  }
}

// v8..v15 source and v24..v27 destination never overlap, even at src m8.
// Keep all live vector state in one asm block; read vstart before vsetvl can
// clear it. Reload VL for the store to observe undisturbed tails, including
// the rest of the physical destination register for fractional LMUL.
#define EXECUTE(INSTRUCTION)                                                    \
  asm volatile(                                                               \
      "vsetvl zero, %[span], %[storetype]\n"                                  \
      "vle8.v v24, (%[initial])\n"                                             \
      "vsetvl zero, %[count], %[type]\n"                                       \
      "vle16.v v8, (%[src])\n"                                                \
      "vlm.v v0, (%[mask])\n"                                                 \
      "vsetvl zero, %[vl], %[type]\n"                                         \
      "csrw frm, %[rm]\n"                                                     \
      "csrw fflags, %[seed]\n"                                                \
      "csrw vstart, %[start]\n"                                               \
      INSTRUCTION "\n"                                                        \
      "csrr %[flags], fflags\n"                                               \
      "csrr %[restart], vstart\n"                                             \
      "csrr %[frm], frm\n"                                                   \
      "vsetvl zero, %[span], %[storetype]\n"                                  \
      "vse8.v v24, (%[result])\n"                                             \
      "fence\n"                                                              \
      "csrr zero, vl\n"                                                       \
      : [flags] "=&r"(got_flags), [restart] "=&r"(got_start),                   \
        [frm] "=&r"(got_rm)                                                    \
      : [span] "r"(span), [storetype] "r"(storetype), [count] "r"(count),      \
        [type] "r"(type), [vl] "r"(vl), [rm] "r"((unsigned long)rm),          \
        [seed] "r"((unsigned long)seed), [start] "r"(start),                    \
        [initial] "r"(initial), [src] "r"(src), [mask] "r"(mask),              \
        [result] "r"(result)                                                   \
      : "memory", "v0", "v8", "v9", "v10", "v11", "v12", "v13", "v14",    \
        "v15", "v24", "v25", "v26", "v27")

#define DISPATCH(OP, NAME)                                                     \
  case OP:                                                                    \
    if (masked) { EXECUTE(NAME " v24, v8, v0.t"); }                            \
    else { EXECUTE(NAME " v24, v8"); }                                        \
    break

static __attribute__((noinline)) void run(unsigned op, unsigned rm, unsigned long type,
                unsigned long count, unsigned long span, unsigned long vl,
                unsigned long start, unsigned masked, unsigned seed) {
  unsigned long got_flags, got_start, got_rm;
  unsigned long storetype = type > 3 ? 0 : type;
  unsigned expected_flags = seed;
  ++cases;
  MEMORY_BARRIER;
  switch (op) {
    DISPATCH(0, "vfncvt.x.f.w");
    DISPATCH(1, "vfncvt.xu.f.w");
    DISPATCH(2, "vfncvt.rtz.x.f.w");
    DISPATCH(3, "vfncvt.rtz.xu.f.w");
  }
  for (unsigned i = 0; i < span; ++i) {
    uint8_t expected = initial[i];
    if (i >= start && i < vl && (!masked || ((mask[i / 8] >> (i % 8)) & 1))) {
      ++active_checks;
      expected = reference(src[i], op & 1, op >= 2 ? RTZ : rm, &expected_flags);
    }
    if (result[i] != expected) {
      printf("FAIL case=%u op=%u rm=%u lmul=%lu vl=%lu start=%lu i=%u "
             "half=%x got=%x expected=%x\n", ordinal - 1, op, rm, type, vl, start,
             i, (unsigned)src[i], (unsigned)result[i], (unsigned)expected);
      ++num_failed;
      return;
    }
  }
  byte_checks += span;
  if (got_flags != expected_flags || got_start != 0 || got_rm != rm) {
    printf("FAIL case=%u op=%u rm=%u lmul=%lu vl=%lu start=%lu "
           "fflags=%lx expected=%x vstart=%lu frm=%lu\n", ordinal - 1, op, rm,
           type, vl, start, got_flags, expected_flags, got_start, got_rm);
    ++num_failed;
  }
  csr_checks += 3;
}

static void prepare(unsigned span, unsigned kind) {
  for (unsigned i = 0; i < span; ++i) {
    src[i] = sample(kind, i);
    initial[i] = (uint8_t)(0xa5 ^ (i * 29));
    result[i] = (uint8_t)~initial[i];
  }
  for (unsigned i = 0; i < (span + 7) / 8; ++i)
    mask[i] = 0xff;
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  cases = ordinal = byte_checks = active_checks = csr_checks = 0;
  for (unsigned i = 0; i < 16; ++i)
    selected_ids[i] = 0;
  unsigned long bytes, saved_fcsr;
  asm volatile("csrr %0, vlenb; csrr %1, fcsr; csrwi vstart, 0"
               : "=r"(bytes), "=r"(saved_fcsr) :: "memory");
  if (bytes < 16 || bytes * 4 > CAP) {
    printf("FAIL unsupported VLEN bytes=%lu (supported 16..2048)\n", bytes);
    return 1;
  }
#if VFNCVT_INT8_SMOKE
  if (bytes != 128) {
    printf("FAIL smoke requires VLEN=1024\n");
    return 1;
  }
#endif

  // 80 batches + 160 isolated boundary conversions. Stripmine the 64-half
  // mixed corpus at small VLEN; use 73 elements at VLEN >= 1024 for odd beats.
  for (unsigned op = 0; op < 4; ++op) {
    for (unsigned rm = RNE; rm <= RMM; ++rm) {
      for (unsigned kind = MIXED; kind <= INVALID; ++kind) {
        unsigned total = kind == MIXED ? 73 : 16;
        for (unsigned offset = 0; offset < total;) {
          unsigned n = total - offset < bytes ? total - offset : bytes;
          if (selected()) {
            prepare(n, kind);
            for (unsigned i = 0; i < n; ++i)
              src[i] = sample(kind, offset + i);
            run(op, rm, 0, n, n, n, 0, 0, 0);
          }
          offset += n;
        }
      }
      for (unsigned i = 0; i < sizeof(boundaries) / sizeof(boundaries[0]); ++i) {
        if (!selected())
          continue;
        prepare(1, EXACT);
        src[0] = boundaries[i];
        run(op, rm, 0, 1, 1, 1, 0, 0, 0);
      }
    }
  }

  // 144 geometry/policy cases. Full VLMAX crosses every source/destination
  // register at integer LMUL. Policies use exact active values and exceptional
  // skipped values so accidental execution cannot hide in aggregate fflags.
  static const unsigned lmuls[] = {5, 6, 7, 0, 1, 2}; // mf8..m4, source mf4..m8
  for (unsigned l = 0; l < 6; ++l) {
    unsigned long type = lmuls[l];
    unsigned long n = type > 3 ? bytes >> (8 - type) : bytes << type;
    unsigned long span = n < bytes ? bytes : n;
    for (unsigned op = 0; op < 4; ++op) {
      for (unsigned policy = 0; policy < 6; ++policy) {
        if (!selected())
          continue;
        unsigned long vl = n, start = 0;
        unsigned masked = policy == 1 || policy == 3;
        prepare(span, policy ? EXACT : MIXED);
        if (policy == 1 || policy == 2) {
          vl = n > 8 ? n - 3 : n - 1;
          start = vl > 5 ? 5 : 1;
        } else if (policy == 4) {
          vl = n - 1;
          start = n; // vstart > vl: absolutely no destination writes
        } else if (policy == 5) {
          vl = 0;
        }
        if (policy == 1 || policy == 3)
          for (unsigned i = 0; i < (span + 7) / 8; ++i)
            mask[i] = policy == 3 ? 0 : (i & 1 ? 0x69 : 0xa6);
        if (policy)
          for (unsigned i = 0; i < span; ++i)
            if (i < start || i >= vl || (masked && !(mask[i / 8] & (1 << (i % 8)))))
              src[i] = i & 1 ? 0x7c01 : 0x3800; // suppressed NV and NX
        run(op, RUP, type, n, span, vl, start, masked, DZ);
      }
    }
  }
#if VFNCVT_INT8_EXTRA_BOUNDARIES
  // Append to preserve the original ordinals. -128, -128.125, -128.25,
  // and -255.5: distinguish signed-minimum rounding from true overflow.
  static const uint16_t extra[] = {0xd800, 0xd801, 0xd802, 0xdbfc};
  for (unsigned op = 0; op < 4; ++op)
    for (unsigned rm = RNE; rm <= RMM; ++rm)
      for (unsigned i = 0; i < 4; ++i) {
        if (!selected())
          continue;
        prepare(1, EXACT);
        src[0] = extra[i];
        run(op, rm, 0, 1, 1, 1, 0, 0, 0);
      }
#endif
  asm volatile("csrw fcsr, %0" :: "r"(saved_fcsr) : "memory");
  printf("vfncvt_int8: %u cases, VLEN=%lu\n", cases, bytes * 8);
  printf("vfncvt_int8_checks: ordinals=%u bytes=%u active=%u csr=%u\n",
         ordinal, byte_checks, active_checks, csr_checks);
  printf("vfncvt_int8_ids:");
  for (unsigned i = 0; i < (ordinal + 63) / 64; ++i)
    printf(" %lx", (unsigned long)selected_ids[i]);
  printf("\n");
  EXIT_CHECK();
}
