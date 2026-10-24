/* The measurement-only drain is an RVV instruction and needs a legal vtype
 * even before the first production primitive has configured its own VL. */
#define main quantized_attention_body
#include "attention_main.c"
#undef main

int main(void) {
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma" : : : "memory");
  return quantized_attention_body();
}
