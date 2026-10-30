#include "schedule_census.h"
#include <assert.h>
#include <stdio.h>
void graph_cache_snapshot(uint64_t values[14]) {
    for (int i=0;i<14;++i) values[i]=(uint64_t)i;
}
int main(void) {
    assert(!graph_schedule_begin(1, 0, 0, 1));
    assert(!graph_schedule_begin(1, 16385, 0, 1));
    assert(!graph_schedule_begin(1, 4, 1, 1));
    assert(!graph_schedule_begin(1, 4, 0, 2));
    assert(graph_schedule_begin(1, 6, 0, 1));
    assert(graph_schedule_append(1, 2, 29));
    assert(graph_schedule_append(4, 5, 25));
    assert(graph_schedule_finish(1));
    assert(!graph_schedule_finish(1));
    assert(graph_schedule_begin(2, 6, 0, 1));
    assert(!graph_schedule_begin(2, 6, 0, 1));
    assert(!graph_schedule_finish(1));
    assert(graph_schedule_begin(3, 6, 0, 1));
    assert(graph_schedule_append(1, 3, 29));
    assert(!graph_schedule_append(3, 4, 25));
    assert(!graph_schedule_finish(1));
    assert(graph_schedule_begin(4, 6, 0, 1));
    assert(!graph_schedule_append(2, 6, 25));
    assert(!graph_schedule_finish(1));
    assert(graph_schedule_begin(5, 6, 0, 1));
    assert(graph_schedule_append(0, 0, 2));
    assert(!graph_schedule_finish(0));
    assert(graph_schedule_begin(6, 1, 0, 1));
    assert(graph_schedule_append(0, 0, 2));
    assert(graph_schedule_finish(1));
    puts("SCHEDULE_CENSUS_HOST_PASS");
    return 0;
}
