#ifndef GRAPH_SCHEDULE_CENSUS_H
#define GRAPH_SCHEDULE_CENSUS_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int graph_schedule_begin(uint64_t epoch, int nodes, int ith, int nth);
int graph_schedule_append(int first, int last, int op);
int graph_schedule_finish(int execution_ok);
void graph_cache_snapshot(uint64_t values[14]);
#ifdef __cplusplus
}
#endif
#endif
