#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "printf.h"
#include "fixture.h"

extern const unsigned char co_data_begin[],co_data_end[],co_data_guard_before[],co_data_guard_after[];
static struct __attribute__((aligned(64))) {
  unsigned char before[64],value[256],after[64];
} outputs[CO_CASES];
static struct {
  uint64_t begin,end,initial_fcsr,initial_vcsr,initial_vstart,fcsr,vcsr,vstart;
  uint64_t detail[3],hash,errors;
} records[CO_CASES];

__attribute__((weak,noinline,noclone)) int co_platform_prepare(void) { return 0; }
__attribute__((weak,noinline,noclone)) int co_platform_check(void) { return 0; }
static uint64_t hash(const void *p,size_t size) {
  const volatile unsigned char *s=p;uint64_t h=UINT64_C(14695981039346656037);
  for (size_t i=0;i<size;++i) h=(h^s[i])*UINT64_C(1099511628211);
  return h;
}
static int guard(const unsigned char *p,size_t size) {
  for (size_t i=0;i<size;++i) if (p[i]!=0xa5) return 1;
  return 0;
}
static uint64_t cycle(void) {
  uint64_t x;__asm__ volatile("rdcycle %0":"=r"(x)::"memory");return x;
}
static void drain(void) {
  uintptr_t x;__asm__ volatile("vmv.x.s %0,v24\nfence rw,rw":"=r"(x)::"memory");
}
static void csrs(uint64_t *f,uint64_t *v,uint64_t *s) {
  __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart":"=r"(*f),"=r"(*v),"=r"(*s)::"memory");
}
int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb!=128 || co_platform_prepare()) {
    printf("CO_REJECT vlenb=%lu\n",vlenb);return 1;
  }
  memset(outputs,0xa5,sizeof(outputs));
  __asm__ volatile("vsetivli zero,1,e32,m1,tu,mu\nvmv.v.i v24,0":::"v24","memory");
  uint64_t errors=0;
  for (unsigned i=0;i<CO_CASES;++i) {
    const co_case_t *c=&co_cases[i];
    if (!CO_CHAIN || !i)
      __asm__ volatile("csrw fcsr,%0\ncsrwi vcsr,5\ncsrwi vstart,0"::"r"((uintptr_t)c->initial_fcsr):"memory");
    drain();csrs(&records[i].initial_fcsr,&records[i].initial_vcsr,&records[i].initial_vstart);
    __asm__ volatile("csrr zero,cycle":::"memory");records[i].begin=cycle();
    c->kernel(outputs[i].value,records[i].detail);
    drain();records[i].end=cycle();__asm__ volatile("csrr zero,cycle":::"memory");
    csrs(&records[i].fcsr,&records[i].vcsr,&records[i].vstart);
  }
  for (unsigned i=0;i<CO_CASES;++i) {
    const co_case_t *c=&co_cases[i];
    records[i].errors=records[i].initial_fcsr!=c->initial_fcsr || records[i].initial_vcsr!=5 ||
        records[i].initial_vstart || records[i].fcsr!=c->fcsr || records[i].vcsr!=5 ||
        records[i].vstart || records[i].detail[0]!=c->vl || records[i].detail[1]!=c->vtype ||
        records[i].detail[2] || records[i].end<=records[i].begin ||
        guard(outputs[i].before,64) || guard(outputs[i].after,64);
    for (unsigned j=0;j<256;++j)
      records[i].errors+=outputs[i].value[j]!=(j<c->bytes?c->gold[j]:0xa5);
    records[i].hash=hash(outputs[i].value,256);
    records[i].errors+=records[i].hash!=c->hash;errors+=records[i].errors;
  }
  errors+=co_platform_check();
  const uint64_t bytes=(uintptr_t)co_data_end-(uintptr_t)co_data_begin;
  const uint64_t data_hash=hash(co_data_begin,bytes);
  errors+=bytes!=CO_DATA_BYTES || data_hash!=CO_DATA_HASH ||
      guard(co_data_guard_before,64) || guard(co_data_guard_after,64);
  for (unsigned i=0;i<CO_CASES;++i)
    printf("CO_CASE id=%u begin=%lu end=%lu initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu fcsr=%lu vcsr=%lu vstart=%lu vl=%lu vtype=%lu op_vstart=%lu hash=%lx errors=%lu\n",
        i,records[i].begin,records[i].end,records[i].initial_fcsr,records[i].initial_vcsr,
        records[i].initial_vstart,records[i].fcsr,records[i].vcsr,records[i].vstart,
        records[i].detail[0],records[i].detail[1],records[i].detail[2],records[i].hash,records[i].errors);
  printf("CO_DATA bytes=%lu hash=%lx\n",bytes,data_hash);
  printf("CO_DONE cases=%u errors=%lu\n",(unsigned)CO_CASES,errors);
  return errors!=0;
}
