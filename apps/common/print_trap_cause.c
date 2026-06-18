
#include <stdint.h>
#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif
void print_trap_cause() {
  int32_t mcause_val;
  int32_t mepc_val;
  int32_t mtval_val;
  int32_t mtvec_val;
  asm volatile("csrr %[mcause_val], mcause" : [mcause_val] "=r"(mcause_val));
  asm volatile("csrr %[mepc_val], mepc  " : [mepc_val] "=r"(mepc_val));
  asm volatile("csrr %[mtval_val], mtval " : [mtval_val] "=r"(mtval_val));
  asm volatile("csrr %[mtvec_val], mtvec " : [mtvec_val] "=r"(mtvec_val));
  printf("mcause_val: %lu\n", mcause_val);
  printf("mepc_val  : %lu\n", mepc_val  );
  printf("mtval_val : %lu\n", mtval_val );
  printf("mtvec_val : %lu\n", mtvec_val );

}
