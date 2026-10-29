/* Arithmetic-domain proof check, not a substitute for RVV/RTL execution. */
#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#pragma STDC FENV_ACCESS ON

int main(void) {
  const int modes[]={FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
  uint64_t checked=0;
  for(unsigned mode=0;mode<sizeof(modes)/sizeof(*modes);++mode) {
    assert(!fesetround(modes[mode]));
    feclearexcept(FE_ALL_EXCEPT);
    feraiseexcept(FE_DIVBYZERO);
    for(unsigned h=0;h<65536;++h) {
      unsigned exponent=(h>>10)&31, fraction=h&1023;
      if(exponent==31) continue; /* Production admission rejects these. */
      int mantissa=exponent?1024+(int)fraction:(int)fraction;
      int power=exponent?(int)exponent-25:-24;
      float scale=ldexpf((float)mantissa,power);
      if(h&32768) scale=-scale;
      for(int x=-128;x<=127;++x) {
        volatile float converted=(float)x;
        volatile float product=scale*converted;
        int exact_integer=mantissa*x;
        if(h&32768) exact_integer=-exact_integer;
        long double expected=ldexpl((long double)exact_integer,power);
        assert((long double)product==expected);
        if(!exact_integer) assert(!!signbit(product)==(!!(h&32768)^(x<0)));
        ++checked;
      }
    }
    assert(fetestexcept(FE_ALL_EXCEPT)==FE_DIVBYZERO);
  }
  assert(!fesetround(FE_TONEAREST));
  printf("Q8_VALUE_DOMAIN_PASS products=%llu finite_half_patterns=63488 int8_values=256 rounding_modes=4 sticky_flags=1\n",
         (unsigned long long)checked);
  return 0;
}
