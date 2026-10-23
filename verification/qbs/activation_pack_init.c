#define main pack_candidate_main
#include "test_activation_pack_candidate.c"
#undef main
#include <sys/reboot.h>
#include <unistd.h>

int main(void) {
    int result = pack_candidate_main();
    printf("PACK_GUEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
