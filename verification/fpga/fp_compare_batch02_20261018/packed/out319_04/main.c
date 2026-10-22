#include <stdint.h>
extern int packed_main(void);
extern void replay_text(const char *);
int main(void) {uint64_t v; __asm__ volatile("csrr %0,vlenb":"=r"(v));
if(v!=128)return 90;
int rc=packed_main();
if(!rc){replay_text("BOARD_REPLAY_PASS\n");}
return rc;}
