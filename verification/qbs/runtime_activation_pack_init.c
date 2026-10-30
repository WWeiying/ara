#define main runtime_pack_main
#include "test_runtime_activation_pack.c"
#undef main
#include <sys/reboot.h>
#include <unistd.h>

int main(void) {
  const int result = runtime_pack_main();
  printf("RUNTIME_PACK_GUEST_EXIT=%d\n", result);
  fflush(NULL);
  sync();
  reboot(RB_POWER_OFF);
  for (;;) pause();
}
