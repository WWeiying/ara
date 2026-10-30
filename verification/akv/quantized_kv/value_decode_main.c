#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#include "printf.h"
#include <math.h>
#include <stdint.h>

extern const unsigned char decode_value0[], decode_value1[];
extern void dequantize_row_q8_0(const void *, float *, int64_t);
enum { DIM=128, TOKENS=128, HEADS=2, ELEMENTS=DIM*TOKENS*HEADS };
static struct __attribute__((aligned(64))) {
  unsigned char before[64]; float data[ELEMENTS]; unsigned char after[64];
} output;
static float reference[ELEMENTS] __attribute__((aligned(64)));

static uint32_t bits(float x) {
  uint32_t value;
  memcpy(&value, &x, 4);
  return value;
}

static uint64_t cycle(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value));
  return value;
}

static void drain(void) {
  __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw" : : : "memory");
}

static void candidate(const void *x, float *y, int64_t n) {
  akv_quant_q8_0_value(x, y, (size_t)n);
}

static unsigned boundaries(void) {
  const uint16_t scales[] = {0x0000,0x8000,0x0001,0x8001,0x03ff,0x83ff,
      0x0400,0x8400,0x3555,0xb555,0x3c00,0xbc00,0x7bff,0xfbff};
  unsigned char block[34] __attribute__((aligned(64)));
  float original[32] __attribute__((aligned(64))), optimized[32] __attribute__((aligned(64)));
  unsigned errors=0;
  for (unsigned s=0;s<sizeof(scales)/sizeof(scales[0]);++s)
    for (unsigned batch=0;batch<8;++batch) {
      memcpy(block, &scales[s], 2);
      for (unsigned i=0;i<32;++i) block[2+i]=(unsigned char)(batch*32+i);
      __asm__ volatile("csrwi fcsr,0" : : : "memory");
      dequantize_row_q8_0(block, original, 32);
      uintptr_t old_flags, new_flags;
      __asm__ volatile("frcsr %0" : "=r"(old_flags));
      __asm__ volatile("csrwi fcsr,0" : : : "memory");
      candidate(block, optimized, 32);
      drain();
      __asm__ volatile("frcsr %0" : "=r"(new_flags));
      if (old_flags || new_flags) {
        if (!errors) printf("QUANT_VALUE_BOUNDARY_FLAGS scale=%04x batch=%u original=%lu candidate=%lu\n",
            scales[s],batch,(unsigned long)old_flags,(unsigned long)new_flags);
        ++errors;
      }
      for (unsigned i=0;i<32;++i)
        if (bits(original[i]) != bits(optimized[i])) {
          if (!errors) printf("QUANT_VALUE_BOUNDARY_MISMATCH scale=%04x batch=%u index=%u original=%08x candidate=%08x\n",
              scales[s],batch,i,bits(original[i]),bits(optimized[i]));
          ++errors;
        }
    }
  printf("QUANT_VALUE_BOUNDARY scales=14 signed_bytes=256 outputs=3584 exact=1 errors=%u\n", errors);
  return errors;
}

int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128) return 1;
  const unsigned char *const sources[] = {decode_value0, decode_value1};
  const unsigned order[] = {0,1,1,0};
  printf("QUANT_VALUE_CAP profiles=2 heads=2 visible=128 capacity=256 d=128 trials=8\n");
  if (boundaries()) return 1;
  for (unsigned kind=0;kind<2;++kind)
    for (unsigned trial=0;trial<4;++trial) {
      memset(&output, 0xa5, sizeof(output));
      const unsigned optimized=order[trial];
      printf("QUANT_VALUE_BEGIN kind=%u trial=%u optimized=%u\n", kind, trial, optimized);
      __asm__ volatile("csrwi fcsr,0;csrwi vcsr,5" : : : "memory");
      drain();
      const uint64_t start=cycle();
      for (unsigned head=0;head<HEADS;++head)
        for (unsigned token=0;token<TOKENS;++token) {
          const void *row=sources[kind]+(head*256+token)*136;
          float *dest=output.data+(head*TOKENS+token)*DIM;
          if (optimized) candidate(row, dest, DIM);
          else dequantize_row_q8_0(row, dest, DIM);
        }
      drain();
      const uint64_t elapsed=cycle()-start;
      uintptr_t fc,vc;
      __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc), "=r"(vc));
      unsigned errors=fc || vc!=5;
      uint64_t hash=UINT64_C(14695981039346656037);
      for (unsigned i=0;i<ELEMENTS;++i) {
        const uint32_t word=bits(output.data[i]);
        errors += !isfinite(output.data[i]);
        if (trial==0) reference[i]=output.data[i];
        else if (word!=bits(reference[i])) {
          if (!errors) printf("QUANT_VALUE_MISMATCH kind=%u trial=%u index=%u original=%08x candidate=%08x\n",
              kind,trial,i,bits(reference[i]),word);
          ++errors;
        }
        for (unsigned byte=0;byte<4;++byte)
          hash=(hash^((word>>(8*byte))&255u))*UINT64_C(1099511628211);
      }
      for (unsigned i=0;i<64;++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
      printf("QUANT_VALUE_RESULT kind=%u trial=%u optimized=%u cycles=%lu outputs=32768 fcsr=%lu vcsr=%lu hash=%016lx errors=%u\n",
          kind,trial,optimized,(unsigned long)elapsed,(unsigned long)fc,(unsigned long)vc,(unsigned long)hash,errors);
      if (errors) return 1;
    }
  printf("QUANT_VALUE_SUITE_PASS trials=8 actual_outputs=262144 finite_boundary_outputs=3584 exact=1\n");
  return 0;
}
