#include "schedule_census.h"
#include <inttypes.h>
#include <stdio.h>

struct group { int first, last, op; };
static struct group groups[16384];
static uint64_t epoch;
static int count, nodes, active, valid, previous;

int graph_schedule_begin(uint64_t id, int size, int ith, int nth) {
    if (active) { valid = 0; return 0; }
    epoch = id;
    nodes = size;
    count = 0;
    previous = -1;
    active = valid = size > 0 && size <= 16384 && ith == 0 && nth == 1;
    return valid;
}

int graph_schedule_append(int first, int last, int op) {
    if (!active || !valid || count >= nodes || first < 0 || first <= previous ||
        last < first || last >= nodes || op < 0) {
        valid = 0;
        return 0;
    }
    groups[count++] = (struct group){first, last, op};
    previous = last;
    return 1;
}

int graph_schedule_finish(int execution_ok) {
    const int ok = active && valid && execution_ok && count > 0;
    active = 0;
    if (!ok) return 0;
    uint64_t stats[14];
    graph_cache_snapshot(stats);
    printf("GRAPH_SCHEDULE epoch=%" PRIu64 " nodes=%d groups=%d\n", epoch, nodes, count);
    for (int i = 0; i < count; ++i)
        printf("GRAPH_SCHEDULE_GROUP epoch=%" PRIu64 " first=%d last=%d op=%d\n",
               epoch, groups[i].first, groups[i].last, groups[i].op);
    printf("GRAPH_CACHE epoch=%" PRIu64, epoch);
    for (int i = 0; i < 14; ++i) printf(" s%d=%" PRIu64, i, stats[i]);
    putchar('\n');
    return 1;
}
