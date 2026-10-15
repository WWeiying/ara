extern void replay_text(const char *);
extern int vv_start0_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN vv_start0\n");
if(vv_start0_main()){replay_text("BOARD_CASE_FAIL vv_start0\n");return 1;}
replay_text("BOARD_CASE_PASS vv_start0\nBOARD_REPLAY_PASS\n");return 0;}
