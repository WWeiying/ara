#include "command_census.h"
#include "qbs/qbs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

extern unsigned census_mock_calls;
static qbs_descriptor_t descriptor = {.header=0x13579, .weight_base=0x24680};
static qbs_status_t call(const qbs_descriptor_t *d) {
    return qbs_native_execute_command((void *)(uintptr_t)0x1234, d, 4,
        (void *)(uintptr_t)0x5678, (float *)(uintptr_t)0x9abc, 96, 32, 7);
}

int main(void) {
    struct graph_command_record storage[3];
    size_t count = 99;
    memset(storage, 0xa5, sizeof(storage));
    const struct graph_command_record guard = storage[2];
    assert(call(&descriptor) == QBS_STATUS_OK); /* Disabled still executes. */
    assert(!graph_command_census_finish(&count));
    assert(!graph_command_census_begin(NULL, 2));
    assert(!graph_command_census_begin(storage, 0));
    assert(graph_command_census_begin(storage, 2));
    assert(call(&descriptor) == QBS_STATUS_OK);
    assert(call(NULL) == QBS_STATUS_BAD_ARGUMENT);
    assert(graph_command_census_finish(&count) && count == 2);
    assert(storage[0].header == descriptor.header && storage[0].descriptor_present == 1);
    assert(storage[0].m == 4 && storage[0].n == 32 && storage[0].output_stride == 96);
    assert(storage[0].segmented == 7 && storage[0].status == QBS_STATUS_OK);
    assert(storage[0].reserved == 0);
    assert(storage[1].header == 0 && storage[1].descriptor_present == 0);
    assert(storage[1].status == QBS_STATUS_BAD_ARGUMENT);
    assert(!memcmp(&storage[2], &guard, sizeof(guard)));
    assert(graph_command_census_begin(storage, 1));
    assert(call(&descriptor) == QBS_STATUS_OK);
    assert(call(&descriptor) == QBS_STATUS_OK); /* Overflow does not suppress call. */
    assert(!graph_command_census_finish(&count) && count == 1);
    assert(graph_command_census_begin(storage, 2));
    assert(!graph_command_census_begin(storage, 2)); /* Nested capture invalidates. */
    assert(call(&descriptor) == QBS_STATUS_OK);
    assert(!graph_command_census_finish(&count));
    assert(graph_command_census_begin(storage, 2));
    assert(!graph_command_census_finish(NULL));
    assert(graph_command_census_begin(storage, 2));
    assert(call(&descriptor) == QBS_STATUS_OK);
    assert(graph_command_census_finish(&count) && count == 1);
    assert(census_mock_calls == 7);
    puts("COMMAND_CENSUS_HOST_PASS calls=7");
    return 0;
}
