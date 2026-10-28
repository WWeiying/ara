#include <stdarg.h>
#include <stddef.h>

static long linux_write(const char *data, size_t size) {
  register long a0 __asm__("a0") = 1;
  register const char *a1 __asm__("a1") = data;
  register size_t a2 __asm__("a2") = size;
  register long a7 __asm__("a7") = 64;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
  return a0;
}

static void emit(const char *data, size_t size) {
  while (size) {
    long written = linux_write(data, size);
    if (written <= 0)
      return;
    data += written;
    size -= (size_t)written;
  }
}

static size_t number(char *buffer, unsigned long long value, unsigned base,
                     unsigned width, char pad) {
  char digits[32];
  size_t count = 0;
  do {
    unsigned digit = value % base;
    digits[count++] = (char)(digit < 10 ? '0' + digit : 'a' + digit - 10);
    value /= base;
  } while (value);
  while (count < width)
    digits[count++] = pad;
  for (size_t i = 0; i < count; ++i)
    buffer[i] = digits[count - i - 1];
  return count;
}

int printf(const char *format, ...) {
  char output[256];
  size_t used = 0;
  int total = 0;
  va_list args;
  va_start(args, format);
  while (*format) {
    if (*format != '%') {
      output[used++] = *format++;
    } else {
      ++format;
      char pad = ' ';
      if (*format == '0') {
        pad = '0';
        ++format;
      }
      unsigned width = 0;
      while (*format >= '0' && *format <= '9')
        width = width * 10 + (unsigned)(*format++ - '0');
      int is_long = *format == 'l';
      if (is_long)
        ++format;
      char specifier = *format++;
      if (specifier == 's') {
        const char *s = va_arg(args, const char *);
        while (*s)
          output[used++] = *s++;
      } else if (specifier == 'c') {
        output[used++] = (char)va_arg(args, int);
      } else if (specifier == 'd' || specifier == 'i') {
        long long signed_value = is_long ? va_arg(args, long) : va_arg(args, int);
        unsigned long long magnitude = (unsigned long long)signed_value;
        if (signed_value < 0) {
          output[used++] = '-';
          magnitude = 0 - magnitude;
        }
        used += number(output + used, magnitude, 10, width, pad);
      } else if (specifier == 'u' || specifier == 'x' || specifier == 'X') {
        unsigned long long value = is_long ? va_arg(args, unsigned long)
                                           : va_arg(args, unsigned int);
        used += number(output + used, value, specifier == 'u' ? 10 : 16,
                       width, pad);
      } else if (specifier == '%') {
        output[used++] = '%';
      }
    }
    if (used > sizeof(output) - 40) {
      emit(output, used);
      total += (int)used;
      used = 0;
    }
  }
  va_end(args);
  emit(output, used);
  return total + (int)used;
}

__attribute__((noreturn)) void _start(void);
__asm__(".global _start\n"
        "_start:\n"
        ".option push\n"
        ".option norelax\n"
        "la gp, __global_pointer$\n"
        ".option pop\n"
        "call main\n"
        "li a7, 93\n"
        "ecall\n"
        "1: j 1b\n");
