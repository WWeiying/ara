#include "akv/akv.h"

static void puts_uart(const char *s) {
  volatile unsigned char *uart = (void *)0x10000000UL;
  while (*s) {
    while (!(uart[5] & 0x20)) {}
    uart[0] = (unsigned char)*s++;
  }
}

static void hex64(uint64_t n) {
  static const char digits[] = "0123456789abcdef";
  char s[17];
  for (unsigned i = 0; i < 16; ++i)
    s[i] = digits[(n >> (60 - i * 4)) & 15];
  s[16] = 0;
  puts_uart(s);
}

static __attribute__((noreturn)) void finish(unsigned code) {
  __asm__ volatile("fence iorw, iorw" ::: "memory");
  *(volatile uint32_t *)0x100000UL = (code << 16) | 0x3333;
  for (;;) __asm__ volatile("wfi");
}

void *memset(void *p, int c, size_t n) {
  unsigned char *b = p;
  for (size_t i = 0; i < n; ++i) b[i] = (unsigned char)c;
  return p;
}

void probe_trap(uint64_t cause, uint64_t pc, uint64_t value) {
  puts_uart("AKV_PROBE_TRAP cause="); hex64(cause);
  puts_uart(" pc="); hex64(pc);
  puts_uart(" value="); hex64(value);
  puts_uart("\n");
  finish(2);
}

void probe_main(void) {
  akv_device_t device;
  puts_uart("AKV_PROBE_BEGIN\n");
  const akv_status_t status = akv_device_query(akv_native_info, NULL, &device);
  puts_uart("AKV_PROBE_QUERY status="); hex64(status);
  puts_uart(" panel4="); hex64(device.capabilities.token_axis_column_panel4);
  puts_uart("\n");
  /* Discovery alone is never an Attention functional PASS. */
  puts_uart("AKV_PROBE_STOP numerical_gate_not_run\n");
  finish(3);
}
