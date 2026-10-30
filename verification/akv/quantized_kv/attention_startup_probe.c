#include "qbs/qbs.h"
#include "printf.h"
#include <stdint.h>

int main(void) {
  qbs_device_t device;
  uintptr_t before, after, vl, fc, vc;
  __asm__ volatile("csrr %0,vtype" : "=r"(before));
  if(qbs_device_query(qbs_native_info,0,&device)!=QBS_STATUS_OK) return 1;
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\n"
                   "csrr %0,vtype\ncsrr %1,vl\n"
                   "csrwi fcsr,0\ncsrwi vcsr,5\n"
                   "vmv.v.i v8,0\n"
                   "vmv.x.s zero,v8\nfence rw,rw\n"
                   "frcsr %2\ncsrr %3,vcsr"
                   : "=r"(after),"=r"(vl),"=r"(fc),"=r"(vc) : : "memory","v8");
  unsigned errors=!(before>>63) || after!=0xd0 || vl!=1 || fc!=0 || vc!=5;
  printf("QUANT_ATTN_STARTUP before=%016lx after=%016lx vl=%lu fcsr=%lu vcsr=%lu errors=%u\n",
      (unsigned long)before,(unsigned long)after,(unsigned long)vl,
      (unsigned long)fc,(unsigned long)vc,errors);
  return errors!=0;
}
