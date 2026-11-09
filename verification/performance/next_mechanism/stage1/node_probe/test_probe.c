#define _POSIX_C_SOURCE 200809L
#include "node_probe.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <time.h>

static unsigned ticks;
static int clock_failure;
int __wrap_clock_gettime(clockid_t id, struct timespec *value) {
    assert(id == CLOCK_MONOTONIC);
    if (clock_failure) { errno = ENOSYS; return -1; }
    value->tv_sec = 0;
    value->tv_nsec = (long)(++ticks)*1000;
    return 0;
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const char *mode=argv[1];
    struct stage1_node_probe_record storage[8];
    const int active=strcmp(mode,"off")!=0;
    assert(stage1_node_probe_init(storage, strcmp(mode,"overflow")==0 ? 1 : 8)==0);
    clock_failure=strcmp(mode,"clock")==0;
    int begin=stage1_node_probe_phase_begin(3,"decode",active,
                                           strcmp(mode,"workers")==0 ? 2 : 1);
    if (strcmp(mode,"clock")==0 || strcmp(mode,"workers")==0) assert(begin<0);
    else assert(begin==0);
    int graph=stage1_node_probe_graph_begin(9,5,1,0);
    if (graph && strcmp(mode,"empty")!=0) {
        int64_t ne[4]={32,2,1,1};
        stage1_node_probe_unit_begin(1);
        stage1_node_probe_unit_end(2);
        stage1_node_probe_member(1,4,"MUL_MAT","f32","quote\"name",ne);
        stage1_node_probe_member(2,5,"ADD","f32","fused",ne);
        if (strcmp(mode,"order")==0) stage1_node_probe_unit_begin(1);
        else {
            stage1_node_probe_unit_begin(4);
            stage1_node_probe_unit_end(4);
            stage1_node_probe_member(4,6,"RMS_NORM","f32","norm",ne);
        }
    }
    if (graph) stage1_node_probe_graph_end(strcmp(mode,"execution")!=0);
    int finish=stage1_node_probe_phase_finish(1);
    const int good=!strcmp(mode,"on") || !strcmp(mode,"off") || !strcmp(mode,"empty");
    assert(good ? finish==0 : finish<0);
    if (!active) assert(ticks==0);
    int dumped=stage1_node_probe_dump(stdout);
    assert(good ? dumped==0 : dumped<0);
    return 0;
}
