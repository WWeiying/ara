#include <stdint.h>

#if defined(ARA_FPGA)
static volatile uint32_t *const uart = (volatile uint32_t *)0x03002000u;
#else
extern char fake_uart;
#endif

void _putchar(char character) {
  // VCU118 exposes the Cheshire 16550-compatible UART at 0x03002000.
#if defined(ARA_FPGA)
  while (!(uart[5] & 0x20u)) {
  }
  uart[0] = (uint8_t)character;
#else
  fake_uart = character;
#endif
}
