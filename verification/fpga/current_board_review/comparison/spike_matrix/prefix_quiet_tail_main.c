extern void replay_text(const char *);
extern int prefix_quiet_tail_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN prefix_quiet_tail\n");
if(prefix_quiet_tail_main()){replay_text("BOARD_CASE_FAIL prefix_quiet_tail\n");return 1;}
replay_text("BOARD_CASE_PASS prefix_quiet_tail\nBOARD_REPLAY_PASS\n");return 0;}
