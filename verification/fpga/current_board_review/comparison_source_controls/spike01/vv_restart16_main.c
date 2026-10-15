extern void replay_text(const char *);
extern int vv_restart16_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN vv_restart16\n");
if(vv_restart16_main()){replay_text("BOARD_CASE_FAIL vv_restart16\n");return 1;}
replay_text("BOARD_CASE_PASS vv_restart16\nBOARD_REPLAY_PASS\n");return 0;}
