#include <stdint.h>
#include <stddef.h>

enum { PREP_RECORDS = 6 };
typedef struct {
  uint32_t probability[2][64], scale[2];
  uint16_t seed[2][128], source[384];
  uint64_t issue_cycles, dump_cycles, fcsr_before, fcsr_after, tokens, dimension;
} prep_record_t;
static prep_record_t prep_records[PREP_RECORDS] __attribute__((aligned(64)));
static unsigned prep_count, prep_errors;
int resident_pv_rotation_always = 1;

/* Preserve the sealed caller, real model data and complete-call checks. */
#define main resident_accepted_main
#include "../rotation/main.c"
#undef main

uint16_t *resident_prepare_before(const uint32_t *probability, const uint16_t *seed,
                                 const uint32_t *scale, size_t tokens, size_t dimension) {
  if (prep_count >= PREP_RECORDS || tokens == 0 || tokens > 64 || dimension != 128) {
    prep_errors++;
    return prep_records[PREP_RECORDS-1].source;
  }
  prep_record_t *r = &prep_records[prep_count++];
  __asm__ volatile("frcsr %0" : "=r"(r->fcsr_before) : : "memory");
  r->tokens=tokens; r->dimension=dimension;
  for (unsigned h=0; h<2; h++) {
    r->scale[h]=scale[h];
    for (unsigned i=0; i<tokens; i++) r->probability[h][i]=probability[64*h+i];
    for (unsigned i=0; i<dimension; i++) r->seed[h][i]=seed[256*h+i];
  }
  return r->source;
}

void resident_prepare_after(uint64_t issue, uint64_t dump, uint64_t fcsr) {
  if (!prep_count || prep_count>PREP_RECORDS) { prep_errors++; return; }
  prep_record_t *r=&prep_records[prep_count-1];
  r->issue_cycles=issue; r->dump_cycles=dump; r->fcsr_after=fcsr;
}

static void emit32(const char *kind, unsigned id, const uint32_t *data, unsigned n) {
  printf("PV_PREP_DATA id=%u kind=%s bits=",id,kind);
  for (unsigned i=0;i<n;i++) printf("%08x",data[i]);
  printf("\n");
}

static void emit16(const char *kind, unsigned id, const uint16_t *data, unsigned n) {
  printf("PV_PREP_DATA id=%u kind=%s bits=",id,kind);
  for (unsigned i=0;i<n;i++) printf("%04x",(unsigned)data[i]);
  printf("\n");
}

int main(void) {
  int rc=resident_accepted_main();
  if (rc) return rc;
  if (prep_count!=PREP_RECORDS) prep_errors++;
  for (unsigned i=0;i<prep_count && i<PREP_RECORDS;i++) {
    const prep_record_t *r=&prep_records[i];
    const unsigned want[3]={64,64,9};
    if (r->tokens!=want[i%3] || r->issue_cycles==0 || r->dump_cycles<r->issue_cycles)
      prep_errors++;
    printf("PV_PREP_META id=%u tokens=%lu dimension=%lu heads=2 issue=%lu dump=%lu fcsr_before=%lu fcsr_after=%lu\n",
           i,r->tokens,r->dimension,r->issue_cycles,r->dump_cycles,r->fcsr_before,r->fcsr_after);
    /* Repeated real calls must have identical inputs and active prepared bits. */
    if (i>=3) {
      const prep_record_t *a=&prep_records[i-3];
      if (memcmp(r->probability,a->probability,sizeof(r->probability)) ||
          memcmp(r->scale,a->scale,sizeof(r->scale)) || memcmp(r->seed,a->seed,sizeof(r->seed)) ||
          memcmp(r->source,a->source,2*128*sizeof(uint16_t)) ||
          memcmp(r->source+256,a->source+256,2*r->tokens*sizeof(uint16_t))) prep_errors++;
    } else {
      emit32("probability",i,&r->probability[0][0],128);
      emit32("scale",i,r->scale,2);
      emit16("seed",i,&r->seed[0][0],256);
      emit16("source",i,r->source,384);
    }
  }
  printf("PV_PREP_COMPLETE records=%u errors=%u\n",prep_count,prep_errors);
  return prep_errors ? 2 : 0;
}
