#include "qbs/qbs.h"
#include <assert.h>

unsigned census_mock_calls;
qbs_status_t qbs_native_execute_command(void *context, const qbs_descriptor_t *d,
    unsigned m, const void *a, float *out, size_t stride, unsigned n, int segmented) {
    assert(context == (void *)(uintptr_t)0x1234);
    assert(a == (void *)(uintptr_t)0x5678 && out == (float *)(uintptr_t)0x9abc);
    assert(m == 4 && n == 32 && stride == 96 && segmented == 7);
    if (d) assert(d->header == 0x13579 && d->weight_base == 0x24680);
    ++census_mock_calls;
    return d ? QBS_STATUS_OK : QBS_STATUS_BAD_ARGUMENT;
}
