#define _POSIX_C_SOURCE 200809L
#include "node_probe.h"

#include <errno.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { EMPTY, READY, RUNNING, FINISHED, DUMPED };
static struct {
    struct stage1_node_probe_record *records;
    size_t capacity, count;
    int state, active, graph_open, unit_open, member_next;
    int nodes, first, last, previous_last, clock_seen, clock_errno;
    uint32_t errors;
    uint64_t id, graphs, epoch, units, fingerprint;
    uint64_t begin, end, clock_last, unit_begin, unit_end, node_sum;
    char name[64];
} probe;

static int result(void) { return probe.errors ? -1 : 0; }

static void hash_bytes(const void *data, size_t size) {
    const unsigned char *bytes = data;
    for (size_t i = 0; i < size; ++i) {
        probe.fingerprint ^= bytes[i];
        probe.fingerprint *= UINT64_C(1099511628211);
    }
}

static void hash_number(uint64_t value) {
    unsigned char bytes[8];
    for (unsigned i = 0; i < 8; ++i) bytes[i] = (unsigned char)(value >> (i * 8));
    hash_bytes(bytes, sizeof(bytes));
}

static int copy_text(char *dst, size_t capacity, const char *src) {
    if (!src) { probe.errors |= STAGE1_NODE_PROBE_API; return 0; }
    size_t length = strnlen(src, capacity);
    if (length == capacity) { probe.errors |= STAGE1_NODE_PROBE_OVERFLOW; return 0; }
    memcpy(dst, src, length + 1);
    return 1;
}

static void hash_text(const char *text) {
    hash_number(strlen(text));
    hash_bytes(text, strlen(text));
}

static uint64_t clock_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        probe.clock_errno = errno;
        probe.errors |= STAGE1_NODE_PROBE_CLOCK;
        if (errno == ENOSYS || errno == ENOTSUP) probe.errors |= STAGE1_NODE_PROBE_UNSUPPORTED;
        return 0;
    }
    if (ts.tv_sec < 0 || ts.tv_nsec < 0 || ts.tv_nsec >= 1000000000L ||
            (uintmax_t)ts.tv_sec > (UINT64_MAX - (uint64_t)ts.tv_nsec) / UINT64_C(1000000000)) {
        probe.errors |= STAGE1_NODE_PROBE_CLOCK;
        return 0;
    }
    uint64_t now = (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
    if (probe.clock_seen && now < probe.clock_last) probe.errors |= STAGE1_NODE_PROBE_CLOCK;
    probe.clock_seen = 1;
    probe.clock_last = now;
    return now;
}

static int quiet(void) {
    /* Pinned QBS_TRACE only prints aggregate counters at exit. Per-call,
     * tensor and lifecycle logs remain forbidden inside measured phases. */
    const char *names[] = {"GGML_RISCV_MODEL_TRACE", "GGML_RISCV_MODEL_DIGEST",
        "GGML_RISCV_MODEL_DUMP_F32", "GGML_RISCV_QBS_TRACE_TENSORS", "GGML_RISCV_QBS_TRACE_CALLS",
        "GGML_RISCV_QBS_TRACE_LIFETIME", "GGML_RISCV_QBS_TRACE_M4_PREPARE", "GGML_RISCV_AKV_TRACE"};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        const char *value = getenv(names[i]);
        if (value && value[0] && strcmp(value, "0") != 0) return 0;
    }
    return 1;
}

uint32_t stage1_node_probe_errors(void) { return probe.errors; }

int stage1_node_probe_init(struct stage1_node_probe_record *records, size_t capacity) {
    if (probe.state == RUNNING) { probe.errors |= STAGE1_NODE_PROBE_API; return -1; }
    memset(&probe, 0, sizeof(probe));
    probe.state = READY;
    probe.records = records;
    probe.capacity = capacity;
    if (!records || !capacity || capacity > SIZE_MAX / sizeof(*records))
        probe.errors |= STAGE1_NODE_PROBE_OVERFLOW;
    return result();
}

int stage1_node_probe_phase_begin(uint64_t id, const char *name, int active, int workers) {
    if (probe.state != READY && probe.state != DUMPED) {
        probe.errors |= STAGE1_NODE_PROBE_API;
        return -1;
    }
    struct stage1_node_probe_record *records = probe.records;
    size_t capacity = probe.capacity;
    (void)stage1_node_probe_init(records, capacity);
    probe.state = RUNNING;
    probe.id = id;
    probe.active = active == 1;
    probe.fingerprint = UINT64_C(14695981039346656037);
    if (active != 0 && active != 1) probe.errors |= STAGE1_NODE_PROBE_API;
    if (workers != 1 || !quiet()) probe.errors |= STAGE1_NODE_PROBE_UNSUPPORTED;
    (void)copy_text(probe.name, sizeof(probe.name), name);
    if (probe.active && !probe.errors) probe.begin = clock_ns();
    return result();
}

int stage1_node_probe_graph_begin(uint64_t epoch, int nodes, int workers, int observing) {
    if (probe.state != RUNNING) return 0;
    if (workers != 1 || observing) probe.errors |= STAGE1_NODE_PROBE_UNSUPPORTED;
    if (nodes < 0 || probe.graph_open) probe.errors |= STAGE1_NODE_PROBE_ORDER;
    if (probe.errors) return 0;
    if (probe.graphs == UINT64_MAX) { probe.errors |= STAGE1_NODE_PROBE_OVERFLOW; return 0; }
    ++probe.graphs;
    probe.graph_open = 1;
    probe.epoch = epoch;
    probe.nodes = nodes;
    probe.previous_last = -1;
    hash_text("graph");
    hash_number((uint64_t)nodes);
    return 1;
}

void stage1_node_probe_unit_begin(int first) {
    if (probe.errors) return;
    if (!probe.graph_open || probe.unit_open || first <= probe.previous_last || first >= probe.nodes) {
        probe.errors |= STAGE1_NODE_PROBE_ORDER;
        return;
    }
    probe.unit_open = 1;
    probe.first = first;
    probe.member_next = first;
    probe.last = -1;
    probe.unit_begin = probe.active ? clock_ns() : 0;
}

void stage1_node_probe_unit_end(int last) {
    /* Timestamp before metadata copies; no drain, fence, allocation or output. */
    uint64_t end = probe.active && !probe.errors ? clock_ns() : 0;
    if (probe.errors) return;
    if (!probe.unit_open || probe.last != -1 || last < probe.first || last >= probe.nodes) {
        probe.errors |= STAGE1_NODE_PROBE_ORDER;
        return;
    }
    if (probe.units == UINT64_MAX || UINT64_MAX - probe.node_sum < end - probe.unit_begin) {
        probe.errors |= STAGE1_NODE_PROBE_OVERFLOW;
        return;
    }
    ++probe.units;
    probe.last = last;
    probe.unit_end = end;
    probe.node_sum += end - probe.unit_begin;
}

void stage1_node_probe_member(int member, int op, const char *op_name,
        const char *type_name, const char *name, const int64_t ne[4]) {
    if (probe.errors) return;
    if (!probe.unit_open || probe.last < probe.first || member != probe.member_next ||
            member > probe.last || !ne || op < 0) {
        probe.errors |= STAGE1_NODE_PROBE_ORDER;
        return;
    }
    if (probe.count == probe.capacity) { probe.errors |= STAGE1_NODE_PROBE_OVERFLOW; return; }
    struct stage1_node_probe_record *r = &probe.records[probe.count];
    memset(r, 0, sizeof(*r));
    r->graph = probe.graphs;
    r->epoch = probe.epoch;
    r->nodes = probe.nodes;
    r->first = probe.first;
    r->last = probe.last;
    r->member = member;
    r->op = op;
    if (!copy_text(r->op_name, sizeof(r->op_name), op_name) ||
            !copy_text(r->type_name, sizeof(r->type_name), type_name) ||
            !copy_text(r->name, sizeof(r->name), name)) return;
    hash_number((uint64_t)member);
    hash_number((uint64_t)r->first);
    hash_number((uint64_t)r->last);
    hash_number((uint64_t)op);
    for (int i = 0; i < 4; ++i) {
        if (ne[i] < 0) { probe.errors |= STAGE1_NODE_PROBE_ORDER; return; }
        r->ne[i] = ne[i];
        hash_number((uint64_t)ne[i]);
    }
    hash_text(r->op_name);
    hash_text(r->type_name);
    hash_text(r->name);
    if (member == probe.first) { r->begin_ns = probe.unit_begin; r->end_ns = probe.unit_end; }
    ++probe.count;
    ++probe.member_next;
    if (member == probe.last) {
        probe.previous_last = member;
        probe.unit_open = 0;
    }
}

void stage1_node_probe_graph_end(int execution_ok) {
    if (!execution_ok) probe.errors |= STAGE1_NODE_PROBE_EXECUTION;
    if (!probe.graph_open || probe.unit_open) probe.errors |= STAGE1_NODE_PROBE_ORDER;
    probe.graph_open = 0;
}

int stage1_node_probe_phase_finish(int execution_ok) {
    if (probe.state != RUNNING) { probe.errors |= STAGE1_NODE_PROBE_API; return -1; }
    if (probe.active) probe.end = clock_ns();
    if (!execution_ok) probe.errors |= STAGE1_NODE_PROBE_EXECUTION;
    if (probe.graph_open || probe.unit_open) probe.errors |= STAGE1_NODE_PROBE_ORDER;
    if (!probe.graphs) probe.errors |= STAGE1_NODE_PROBE_UNSUPPORTED;
    if (probe.active && !(probe.errors & STAGE1_NODE_PROBE_CLOCK) &&
            (probe.end < probe.begin || probe.node_sum > probe.end - probe.begin))
        probe.errors |= STAGE1_NODE_PROBE_ORDER;
    probe.state = FINISHED;
    return result();
}

static void json_text(FILE *out, const char *text) {
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') { fputc('\\', out); fputc(*p, out); }
        else if (*p < 32) fprintf(out, "\\u%04x", (unsigned)*p);
        else fputc(*p, out);
    }
    fputc('"', out);
}

int stage1_node_probe_dump(FILE *out) {
    if (probe.state != FINISHED || !out) { probe.errors |= STAGE1_NODE_PROBE_API; return -1; }
    fprintf(out, "{\"schema\":\"stage1-node-ns-v1\",\"phase_id\":%" PRIu64 ",\"phase\":", probe.id);
    json_text(out, probe.name);
    fprintf(out, ",\"valid\":%s,\"errors\":%u,\"active\":%s,\"clock_errno\":%d,"
            "\"clock\":\"CLOCK_MONOTONIC\",\"semantics\":\"software_node_elapsed_ns_no_added_sync\","
            "\"graphs\":%" PRIu64 ",\"units\":%" PRIu64 ",\"members\":%zu,"
            "\"path_fingerprint_fnv1a64\":\"%016" PRIx64 "\",\"phase_ns\":",
            probe.errors ? "false" : "true", probe.errors, probe.active ? "true" : "false",
            probe.clock_errno, probe.graphs, probe.units, probe.count, probe.fingerprint);
    if (probe.active && !probe.errors) fprintf(out, "%" PRIu64, probe.end - probe.begin);
    else fputs("null", out);
    fputs(",\"unit_ns\":", out);
    if (probe.active && !probe.errors) fprintf(out, "%" PRIu64, probe.node_sum);
    else fputs("null", out);
    fputs(",\"unattributed_ns\":", out);
    if (probe.active && !probe.errors) fprintf(out, "%" PRIu64, probe.end - probe.begin - probe.node_sum);
    else fputs("null", out);
    fputs(",\"records\":[", out);
    for (size_t i = 0; i < probe.count; ++i) {
        const struct stage1_node_probe_record *r = &probe.records[i];
        if (i) fputc(',', out);
        fprintf(out, "{\"graph\":%" PRIu64 ",\"epoch\":%" PRIu64 ",\"nodes\":%d,"
                "\"first\":%d,\"last\":%d,\"member\":%d,\"op\":%d,\"op_name\":",
                r->graph, r->epoch, r->nodes, r->first, r->last, r->member, r->op);
        json_text(out, r->op_name);
        fputs(",\"type\":", out); json_text(out, r->type_name);
        fputs(",\"name\":", out); json_text(out, r->name);
        fprintf(out, ",\"ne\":[%" PRId64 ",%" PRId64 ",%" PRId64 ",%" PRId64 "],\"elapsed_ns\":",
                r->ne[0], r->ne[1], r->ne[2], r->ne[3]);
        if (probe.active && !probe.errors && r->member == r->first)
            fprintf(out, "%" PRIu64, r->end_ns - r->begin_ns);
        else fputs("null", out);
        fputc('}', out);
    }
    fputs("]}\n", out);
    if (fflush(out) || ferror(out)) probe.errors |= STAGE1_NODE_PROBE_IO;
    probe.state = DUMPED;
    return result();
}
