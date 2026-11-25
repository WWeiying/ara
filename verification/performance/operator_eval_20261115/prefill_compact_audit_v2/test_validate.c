#include "validate.h"
#include <assert.h>

int main(void) {
  static float actual[16384],gold[16384];
  for (unsigned i = 0; i < 16384; ++i) actual[i] = gold[i] = 1.0f;
  compact_check_t r = compact_validate_all(actual,gold,16384);
  assert(r.checked == 16384 && !r.nonfinite && !r.tolerance_errors);
  actual[16383] = 1.007f;
  r = compact_validate_all(actual,gold,16384);
  assert(r.checked == 16384 && !r.nonfinite && r.tolerance_errors == 1);
  actual[16383] = 1.005f;
  r = compact_validate_all(actual,gold,16384);
  assert(!r.nonfinite && !r.tolerance_errors);
  actual[16383] = NAN;
  r = compact_validate_all(actual,gold,16384);
  assert(r.checked == 16384 && r.nonfinite == 1);
  actual[16383] = INFINITY;
  r = compact_validate_all(actual,gold,16384);
  assert(r.nonfinite == 1 && r.tolerance_errors == 1);
  return 0;
}
