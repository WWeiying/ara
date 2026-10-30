#ifndef QBS_GRAPH_CYCLE_RECORDS_H
#define QBS_GRAPH_CYCLE_RECORDS_H

#include <stddef.h>
#include <stdint.h>

/* Caller owns storage and clock reads. No allocation, output or synchronization. */
struct qbs_graph_cycle_record {
    int first, last, op;
    uint64_t begin, end;
};

struct qbs_graph_cycles {
    struct qbs_graph_cycle_record *records;
    size_t capacity, count;
    int nodes, active, valid, last_node;
    uint64_t epoch, begin, end, node_sum;
};

static inline void qbs_graph_cycles_begin(struct qbs_graph_cycles *p,
        struct qbs_graph_cycle_record *records, size_t capacity, int nodes,
        int ith, int nth, uint64_t epoch, uint64_t begin) {
    p->records=records; p->capacity=capacity; p->count=0;
    p->nodes=nodes; p->last_node=-1; p->epoch=epoch;
    p->begin=begin; p->end=begin; p->node_sum=0;
    p->active=records && nodes>=0 && capacity>=(size_t)nodes && ith==0 && nth==1;
    p->valid=p->active;
}

static inline void qbs_graph_cycles_append(struct qbs_graph_cycles *p,
        int first, int last, int op, uint64_t begin, uint64_t end) {
    if (!p->active || !p->valid) return;
    if (p->count>=p->capacity || first<=p->last_node || first<0 ||
        last<first || last>=p->nodes || begin<p->end || end<begin ||
        UINT64_MAX-p->node_sum<end-begin) {
        p->valid=0; return;
    }
    struct qbs_graph_cycle_record *r=&p->records[p->count++];
    r->first=first; r->last=last; r->op=op; r->begin=begin; r->end=end;
    p->last_node=last; p->end=end; p->node_sum+=end-begin;
}

static inline int qbs_graph_cycles_finish(struct qbs_graph_cycles *p,
        uint64_t end, int execution_ok) {
    if (!p->active || !p->valid || !execution_ok || end<p->end ||
        end<p->begin || p->node_sum>end-p->begin) {
        p->valid=0; p->active=0; return 0;
    }
    p->end=end; p->active=0; return 1;
}

#endif
