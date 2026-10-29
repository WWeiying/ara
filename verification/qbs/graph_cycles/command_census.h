#ifndef GRAPH_COMMAND_CENSUS_H
#define GRAPH_COMMAND_CENSUS_H

#include <stddef.h>
#include <stdint.h>

/* Shape/order evidence, not an address/data transcript or hardware retirement. */
struct graph_command_record {
    uint64_t header, output_stride;
    uint32_t m, n;
    int32_t segmented, status;
    uint32_t descriptor_present, reserved;
};

#ifdef __cplusplus
extern "C" {
#endif
/* Single caller only. Storage is allocated by the harness outside inference. */
int graph_command_census_begin(struct graph_command_record *, size_t capacity);
int graph_command_census_finish(size_t *count);
#ifdef __cplusplus
}
#endif

#endif
