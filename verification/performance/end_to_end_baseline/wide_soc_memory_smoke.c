// Standalone ordinary scalar/RVV memory smoke; identical ELF for either bus width.
#include <stddef.h>
#include <stdint.h>
#include "printf.h"

#define PAGE 4096u
#define GUARD 16u
#define MAX_VECTOR_BYTES 512u
#define ARENA_BYTES (2u * PAGE)

typedef size_t (*vector_fn)(void *, const void *, void *, const void *,
                            const uint8_t *, size_t, unsigned);
extern size_t wide_soc_memory_smoke_e8(void *, const void *, void *, const void *, const uint8_t *, size_t, unsigned);
extern size_t wide_soc_memory_smoke_e16(void *, const void *, void *, const void *, const uint8_t *, size_t, unsigned);
extern size_t wide_soc_memory_smoke_e32(void *, const void *, void *, const void *, const uint8_t *, size_t, unsigned);
extern size_t wide_soc_memory_smoke_e64(void *, const void *, void *, const void *, const uint8_t *, size_t, unsigned);
extern size_t wide_soc_memory_smoke_vlmax(unsigned);
extern uint64_t wide_soc_memory_smoke_scalar(unsigned, volatile void *, uint64_t);
extern int64_t wide_soc_memory_smoke_signed(unsigned, const volatile void *);

static volatile uint8_t source[ARENA_BYTES] __attribute__((aligned(PAGE)));
static volatile uint8_t target[ARENA_BYTES] __attribute__((aligned(PAGE)));
static volatile uint8_t scalar_area[ARENA_BYTES] __attribute__((aligned(PAGE)));
static uint8_t seed[MAX_VECTOR_BYTES + 2u * GUARD] __attribute__((aligned(64)));
static volatile uint8_t observed[MAX_VECTOR_BYTES + 2u * GUARD] __attribute__((aligned(64)));
static uint8_t mask[MAX_VECTOR_BYTES / 8u] __attribute__((aligned(64)));

// Main's SoC harness may probe these, but acceptance is the scalar checks below.
volatile uint64_t wide_soc_memory_smoke_phase;
volatile uint64_t wide_soc_memory_smoke_failures;
volatile uint64_t wide_soc_memory_smoke_scalar_cases;
volatile uint64_t wide_soc_memory_smoke_vector_cases;
static uint64_t digest_value;
static unsigned byte_checks, value_checks, source_crossings, target_crossings;
static unsigned context_eew, context_phase, context_mode;

static uint64_t cycle(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value));
  return value;
}

static uint8_t pattern(unsigned salt, unsigned test, unsigned byte) {
  return (uint8_t)(salt + test * 29u + byte * 37u + byte / 7u);
}

static int fail(unsigned stage, unsigned byte, uint64_t got, uint64_t expected) {
  ++wide_soc_memory_smoke_failures;
  printf("WIDE_SOC_MEMORY_SMOKE_FAIL stage=%u eew=%u phase=%u mode=%u byte=%u got=%08x%08x expected=%08x%08x\n",
         stage, context_eew, context_phase, context_mode, byte,
         (unsigned)(got >> 32), (unsigned)got, (unsigned)(expected >> 32), (unsigned)expected);
  return 1;
}

static int check_byte(unsigned stage, unsigned byte, uint8_t got, uint8_t expected) {
  ++byte_checks;
  if (got != expected) return fail(stage, byte, got, expected);
  digest_value = (digest_value ^ got) * UINT64_C(1099511628211);
  return 0;
}

static int scalar_cases(void) {
  unsigned test = 0;
  for (unsigned log_bytes = 0; log_bytes < 4; ++log_bytes) {
    const unsigned bytes = 1u << log_bytes;
    context_eew = 8u * bytes;
    for (unsigned phase = 0; phase < 32; phase += bytes) {
      for (unsigned position = 0; position < 3; ++position) {
        const unsigned at = (position == 0 ? PAGE - 32u : position == 1 ? PAGE : 32u) + phase;
        const unsigned start = at - GUARD, span = bytes + 2u * GUARD;
        uint64_t value = UINT64_C(0xfedcba9876543210) ^ ((uint64_t)test * UINT64_C(0x01030507090b0d0f));
        value = position == 0 ? value | UINT64_C(0x8080808080808080) :
                position == 1 ? value & UINT64_C(0x7f7f7f7f7f7f7f7f) : value;
        const uint64_t expected = bytes == 8 ? value : value & ((UINT64_C(1) << (8u * bytes)) - 1u);
        const unsigned shift = 64u - 8u * bytes;
        const int64_t signed_expected = (int64_t)(expected << shift) >> shift;
        context_phase = phase; context_mode = position;
        for (unsigned i = 0; i < span; ++i) scalar_area[start+i] = pattern(0x69u, test, i);
        const uint64_t got = wide_soc_memory_smoke_scalar(log_bytes, &scalar_area[at], value);
        ++value_checks;
        if (got != expected) return fail(1, 0, got, expected);
        const int64_t signed_got = wide_soc_memory_smoke_signed(log_bytes, &scalar_area[at]);
        ++value_checks;
        if (signed_got != signed_expected) return fail(2, 0, (uint64_t)signed_got, (uint64_t)signed_expected);
        for (unsigned i = 0; i < span; ++i) {
          const uint8_t want = i >= GUARD && i < GUARD + bytes ?
              (uint8_t)(value >> (8u * (i - GUARD))) : pattern(0x69u, test, i);
          if (check_byte(3, i, scalar_area[start+i], want)) return 1;
        }
        ++wide_soc_memory_smoke_scalar_cases; ++test;
      }
    }
  }
  return 0;
}

static int active(unsigned mode, unsigned lane, unsigned vl, unsigned phase_index) {
  if (lane >= vl) return 0;
  if (mode == 0) return 1;
  if (mode == 1) return ((lane + phase_index) & 1u) == 0;
  if (mode == 2) return ((lane + phase_index) & 1u) != 0;
  return lane == 0 || lane + 1u == vl || lane % 5u == 2u;
}

static int vector_cases(unsigned vector_bytes) {
  const vector_fn functions[4] = {wide_soc_memory_smoke_e8, wide_soc_memory_smoke_e16,
                                  wide_soc_memory_smoke_e32, wide_soc_memory_smoke_e64};
  unsigned test = 0;
  for (unsigned log_bytes = 0; log_bytes < 4; ++log_bytes) {
    const unsigned bytes = 1u << log_bytes;
    const size_t maximum = wide_soc_memory_smoke_vlmax(log_bytes);
    context_eew = 8u * bytes;
    if (maximum * bytes != vector_bytes) return fail(4, 0, maximum * bytes, vector_bytes);
    for (unsigned phase = 0; phase < 32; phase += bytes) {
      for (unsigned mode = 0; mode < 4; ++mode) {
        const unsigned vl = mode == 0 ? (unsigned)maximum : mode == 1 ? (unsigned)maximum - 1u :
                            mode == 2 ? 1u : ((unsigned)maximum + 1u) / 2u;
        const unsigned src = PAGE - 16u + phase, dst = PAGE - 16u + (phase + 16u) % 32u;
        const unsigned span = vector_bytes + 2u * GUARD;
        const int undisturbed = mode == 1 || mode == 3;
        const unsigned flags = (mode != 0 ? 1u : 0u) | (undisturbed ? 2u : 0u);
        context_phase = phase; context_mode = mode;
        for (unsigned i = 0; i < span; ++i) {
          source[src-GUARD+i] = pattern(0x31u, test, i);
          target[dst-GUARD+i] = pattern(0x57u, test, i);
          seed[i] = pattern(0x91u, test, i);
          observed[i] = pattern(0xc3u, test, i);
        }
        for (unsigned i = 0; i < sizeof(mask); ++i) mask[i] = 0;
        for (unsigned i = 0; i < (unsigned)maximum; ++i)
          if (active(mode, i, vl, phase / bytes)) mask[i / 8u] |= (uint8_t)(1u << (i % 8u));
        __asm__ volatile("fence rw, rw" ::: "memory");
        const size_t got_vl = functions[log_bytes]((void *)&target[dst], (const void *)&source[src],
            (void *)&observed[GUARD], &seed[GUARD], mask, vl, flags);
        if (got_vl != vl) return fail(5, 0, got_vl, vl);
        if (src < PAGE && src + vl * bytes > PAGE) ++source_crossings;
        if (dst < PAGE && dst + vl * bytes > PAGE) ++target_crossings;
        for (unsigned i = 0; i < span; ++i) {
          const int payload = i >= GUARD && i < GUARD + vector_bytes;
          const unsigned lane = payload ? (i - GUARD) / bytes : 0;
          const int selected = payload && active(mode, lane, vl, phase / bytes);
          if (check_byte(6, i, source[src-GUARD+i], pattern(0x31u, test, i))) return 1;
          if (check_byte(7, i, target[dst-GUARD+i], pattern(selected ? 0x31u : 0x57u, test, i))) return 1;
          // Only tu/mu makes inactive register contents comparable. Memory
          // outside an instruction's active stores must always stay unchanged.
          if (!payload || selected || undisturbed) {
            const unsigned salt = !payload ? 0xc3u : selected ? 0x31u : 0x91u;
            if (check_byte(8, i, observed[i], pattern(salt, test, i))) return 1;
          }
        }
        ++wide_soc_memory_smoke_vector_cases; ++test;
      }
    }
  }
  return 0;
}

int main(void) {
  unsigned long vector_bytes;
  wide_soc_memory_smoke_phase = 1;
  wide_soc_memory_smoke_failures = 0;
  wide_soc_memory_smoke_scalar_cases = 0;
  wide_soc_memory_smoke_vector_cases = 0;
  byte_checks = value_checks = source_crossings = target_crossings = 0;
  digest_value = UINT64_C(0xcbf29ce484222325);
  printf("WIDE_SOC_MEMORY_SMOKE_BEGIN version=1\n");
  const uint64_t start = cycle();
  __asm__ volatile("csrr %0, vlenb" : "=r"(vector_bytes));
  int failed = 0;
  if (vector_bytes < 32u || vector_bytes > MAX_VECTOR_BYTES || (vector_bytes & (vector_bytes - 1u)))
    failed = fail(9, 0, vector_bytes, MAX_VECTOR_BYTES);
  wide_soc_memory_smoke_phase = 2;
  if (!failed) failed = scalar_cases();
  wide_soc_memory_smoke_phase = 3;
  if (!failed) failed = vector_cases((unsigned)vector_bytes);
  if (!failed && (wide_soc_memory_smoke_scalar_cases != 180 || wide_soc_memory_smoke_vector_cases != 240 ||
                  value_checks != 360 || source_crossings == 0 || target_crossings == 0))
    failed = fail(10, 0, wide_soc_memory_smoke_vector_cases, 240);
  const uint64_t end = cycle();
  wide_soc_memory_smoke_phase = failed ? 5 : 4;
  printf("WIDE_SOC_MEMORY_SMOKE_END status=%s cycles=%lu\n", failed ? "FAIL" : "PASS", (unsigned long)(end-start));
  if (failed) return 1;
  printf("WIDE_SOC_MEMORY_SMOKE_PASS scalar_cases=180 vector_cases=240 value_checks=360 byte_checks=%u vlenb=%u vector_insns=1924 source_crossings=%u target_crossings=%u digest=%08x%08x\n",
         byte_checks, (unsigned)vector_bytes, source_crossings, target_crossings,
         (unsigned)(digest_value >> 32), (unsigned)digest_value);
  return 0;
}
