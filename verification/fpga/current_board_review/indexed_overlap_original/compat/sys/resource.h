#ifndef IO_RESOURCE_H
#define IO_RESOURCE_H
#ifdef IO_HOST
#include_next <sys/resource.h>
#else
// RV64 Linux rusage layout; the local service implements only ru_minflt.
struct io_timeval { long tv_sec, tv_usec; };
struct rusage {
    struct io_timeval ru_utime, ru_stime;
    long ru_maxrss, ru_ixrss, ru_idrss, ru_isrss, ru_minflt, ru_majflt;
    long ru_nswap, ru_inblock, ru_oublock, ru_msgsnd, ru_msgrcv;
    long ru_nsignals, ru_nvcsw, ru_nivcsw;
};
_Static_assert(__builtin_offsetof(struct rusage, ru_minflt)==64,"RV64 ABI offset");
_Static_assert(sizeof(struct rusage)==144,"RV64 ABI size");
#endif
#endif
