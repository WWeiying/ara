#ifndef FIXED10752_PORT_H
#define FIXED10752_PORT_H

/* Same bare source-port service boundary as the accepted prefix, not Linux. */
extern long replay_write(long number, long fd, long pointer, long length);
static long syscall3(long n, long x, long y, long z) {
    /* No Linux tty or TCSBRK exists here. Preserve all boundary text calls. */
    if (n == 29 && x == 1 && y == 0x5409 && z == 1) return 0;
    return replay_write(n, x, y, z);
}

#if !defined(__riscv)
/* A later Host harness must supply the actual intended capacity explicitly. */
extern unsigned long fixed_host_vlenb(void);
#endif
#endif
