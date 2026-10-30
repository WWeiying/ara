#ifndef AKV_QUANT_FAST_HEX32_H
#define AKV_QUANT_FAST_HEX32_H

#include <stdint.h>

void _putchar(char character);

/* Exactly the eight lowercase characters of printf("%08x", value). */
static inline void fast_hex32(uint32_t value) {
  static const char digits[] = "0123456789abcdef";
  _putchar(digits[(value >> 28) & 15u]);
  _putchar(digits[(value >> 24) & 15u]);
  _putchar(digits[(value >> 20) & 15u]);
  _putchar(digits[(value >> 16) & 15u]);
  _putchar(digits[(value >> 12) & 15u]);
  _putchar(digits[(value >> 8) & 15u]);
  _putchar(digits[(value >> 4) & 15u]);
  _putchar(digits[value & 15u]);
}

#endif
