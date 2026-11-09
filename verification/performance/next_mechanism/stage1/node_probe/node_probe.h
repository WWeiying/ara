#ifndef STAGE1_NODE_PROBE_H
#define STAGE1_NODE_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

enum stage1_node_probe_error {
    STAGE1_NODE_PROBE_API = 1u,
    STAGE1_NODE_PROBE_UNSUPPORTED = 2u,
    STAGE1_NODE_PROBE_OVERFLOW = 4u,
    STAGE1_NODE_PROBE_CLOCK = 8u,
    STAGE1_NODE_PROBE_ORDER = 16u,
    STAGE1_NODE_PROBE_EXECUTION = 32u,
    STAGE1_NODE_PROBE_IO = 64u
};

/* One record per executed member, including every member of a fused unit.
 * Only the first member owns begin_ns/end_ns; followers must not be summed. */
struct stage1_node_probe_record {
    uint64_t graph, epoch, begin_ns, end_ns;
    int nodes, first, last, member, op;
    int64_t ne[4];
    char op_name[64], type_name[32], name[64];
};

/* Single caller/CPU worker; storage must outlive finish AND dump. No allocation.
 * active=0 collects the same path but performs no clock reads, including phase
 * boundaries. active=1 uses CLOCK_MONOTONIC nanoseconds, not hardware cycles.
 * Call finish only after llama_decode AND llama_synchronize have returned.
 * Dump is explicit, outside the ROI, and required before the next phase. */
int stage1_node_probe_init(struct stage1_node_probe_record *records, size_t capacity);
int stage1_node_probe_phase_begin(uint64_t id, const char *name, int active, int workers);
int stage1_node_probe_phase_finish(int execution_ok);
int stage1_node_probe_dump(FILE *output);
uint32_t stage1_node_probe_errors(void);

/* Instrumented CPU-loop hooks. Not frontend entry points. */
int stage1_node_probe_graph_begin(uint64_t epoch, int nodes, int workers, int observing);
void stage1_node_probe_unit_begin(int first);
void stage1_node_probe_unit_end(int last);
void stage1_node_probe_member(int member, int op, const char *op_name,
        const char *type_name, const char *name, const int64_t ne[4]);
void stage1_node_probe_graph_end(int execution_ok);

#ifdef __cplusplus
}
#endif
#endif
