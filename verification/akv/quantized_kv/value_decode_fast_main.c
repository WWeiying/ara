/* Reuse the sealed kernel, fixtures and all directed boundary diagnostics.
 * Only the measurement/check harness below is replaced. */
#define main archived_byte_hash_main
#include "value_decode_main.c"
#undef main

static uint32_t raw_word(const float *value) {
  uint32_t result;
  __builtin_memcpy(&result,value,4);
  return result;
}

static uint64_t reference_word_hash(void) {
  uint64_t hash=UINT64_C(14695981039346656037);
  for(unsigned i=0;i<ELEMENTS;++i)
    hash=(hash^raw_word(reference+i))*UINT64_C(1099511628211);
  return hash;
}

int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if(vlenb!=128) return 1;
  const unsigned char *const sources[]={decode_value0,decode_value1};
  const unsigned order[]={0,1,1,0};
  printf("QUANT_VALUE_FAST_CAP profiles=2 heads=2 visible=128 capacity=256 d=128 trials=8 hash=word_fnv64\n");
  if(boundaries()) return 1;
  for(unsigned kind=0;kind<2;++kind) {
    for(unsigned trial=0;trial<4;++trial) {
      memset(&output,0xa5,sizeof(output));
      const unsigned optimized=order[trial];
      printf("QUANT_VALUE_FAST_BEGIN kind=%u trial=%u optimized=%u\n",kind,trial,optimized);
      __asm__ volatile("csrwi fcsr,0;csrwi vcsr,5" : : : "memory");
      drain();
      const uint64_t start=cycle();
      for(unsigned head=0;head<HEADS;++head)
        for(unsigned token=0;token<TOKENS;++token) {
          const void *row=sources[kind]+(head*256+token)*136;
          float *dest=output.data+(head*TOKENS+token)*DIM;
          if(optimized) candidate(row,dest,DIM);
          else dequantize_row_q8_0(row,dest,DIM);
        }
      drain();
      const uint64_t elapsed=cycle()-start;
      uintptr_t fc,vc;
      __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc),"=r"(vc));
      unsigned errors=fc || vc!=5;
      for(unsigned i=0;i<ELEMENTS;++i) {
        const uint32_t word=raw_word(output.data+i);
        errors+=(word&UINT32_C(0x7f800000))==UINT32_C(0x7f800000);
        if(trial==0) __builtin_memcpy(reference+i,&word,4);
        else if(word!=raw_word(reference+i)) {
          if(!errors) printf("QUANT_VALUE_FAST_MISMATCH kind=%u trial=%u index=%u original=%08x candidate=%08x\n",
                            kind,trial,i,raw_word(reference+i),word);
          ++errors;
        }
      }
      for(unsigned i=0;i<64;++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
      printf("QUANT_VALUE_FAST_RESULT kind=%u trial=%u optimized=%u cycles=%lu outputs=32768 fcsr=%lu vcsr=%lu compared=32768 errors=%u\n",
          kind,trial,optimized,(unsigned long)elapsed,(unsigned long)fc,(unsigned long)vc,errors);
      if(errors) return 1;
    }
    /* Each subsequent trial was independently compared word by word with this
     * immutable first-original reference. Hash it once, outside every timer. */
    printf("QUANT_VALUE_FAST_HASH kind=%u outputs=32768 hash=%016lx\n",kind,(unsigned long)reference_word_hash());
  }
  printf("QUANT_VALUE_FAST_SUITE_PASS trials=8 actual_outputs=262144 finite_boundary_outputs=3584 exact=1\n");
  return 0;
}
