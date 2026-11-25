#define main previous_csr_cases
#include "old_client_csr.c"
#undef main

long ara_resident_linux_execute_batch_scalar(int fd, struct ara_resident_batch *b)
{
    (void)fd;
    ++calls;
    b->fflags = 5;
    b->completed = b->count;
    asm volatile("csrwi fcsr,0;csrwi vcsr,0" ::: "memory");
    return code;
}

int main(void)
{
    int old = previous_csr_cases();
    if (old) return old;
    static struct ara_resident_batch b;
    b.count = 16;
    for (unsigned frm = 0; frm < 5; ++frm)
        for (unsigned v = 0; v < 8; ++v)
            for (unsigned fail = 0; fail < 2; ++fail) {
                unsigned f = (frm << 5) | 16;
                code = fail ? -5 : 0;
                asm volatile("csrw fcsr,%0;csrw vcsr,%1" :: "r"(f), "r"(v) : "memory");
                if (ara_resident_linux_execute_batch(9, &b) != code ||
                    csr(0) != (fail ? f : f | 5) || csr(1) != v || csr(2)) return 4;
                unsigned before = calls;
                asm volatile("csrwi vstart,3" ::: "memory");
                if (ara_resident_linux_execute_batch(9, &b) != -34 || calls != before ||
                    csr(0) != (fail ? f : f | 5) || csr(1) != v || csr(2) != 3) return 5;
                asm volatile("csrwi vstart,0" ::: "memory");
            }
    return calls != 82;
}
