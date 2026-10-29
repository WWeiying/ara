#include "command_census.h"
#include "qbs/qbs.h"

static struct graph_command_record *records;
static size_t capacity, count;
static int active, valid;

int graph_command_census_begin(struct graph_command_record *storage, size_t size) {
    if (active) {
        valid = 0;
        return 0;
    }
    records = storage;
    capacity = size;
    count = 0;
    active = valid = storage != NULL && size != 0;
    return valid;
}

int graph_command_census_finish(size_t *out_count) {
    if (out_count) *out_count = count;
    const int ok = active && valid && out_count != NULL;
    active = 0;
    return ok;
}

qbs_status_t __real_qbs_native_execute_command(void *, const qbs_descriptor_t *,
    unsigned, const void *, float *, size_t, unsigned, int);

qbs_status_t __wrap_qbs_native_execute_command(void *context,
    const qbs_descriptor_t *descriptor, unsigned m, const void *activations,
    float *output, size_t stride, unsigned n, int segmented) {
    struct graph_command_record *record = NULL;
    if (active && valid) {
        if (count == capacity) {
            valid = 0;
        } else {
            record = &records[count++];
            record->header = descriptor ? descriptor->header : 0;
            record->output_stride = stride;
            record->m = m;
            record->n = n;
            record->segmented = segmented;
            record->descriptor_present = descriptor != NULL;
            record->reserved = 0;
        }
    }
    /* Forward even when capture is disabled/invalid/full; never change work. */
    const qbs_status_t status = __real_qbs_native_execute_command(context,
        descriptor, m, activations, output, stride, n, segmented);
    if (record) record->status = status;
    return status;
}
