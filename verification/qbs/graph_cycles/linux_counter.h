#ifndef GRAPH_CYCLES_LINUX_COUNTER_H
#define GRAPH_CYCLES_LINUX_COUNTER_H

#include <linux/perf_event.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Isolated single-hart test only: keep the fixed cycle counter running across
 * child execution and scheduling. Requires privileged system-wide perf access
 * and Linux's explicit user-counter permission; not a runtime library change. */
static int graph_cycles_linux_counter_start(void) {
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type = PERF_TYPE_HARDWARE;
    attr.size = sizeof(attr);
    attr.config = PERF_COUNT_HW_CPU_CYCLES;
    attr.pinned = 1;
    return (int)syscall(__NR_perf_event_open, &attr, -1, 0, -1, 0);
}

#endif
