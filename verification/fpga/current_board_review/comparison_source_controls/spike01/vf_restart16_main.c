extern void replay_text(const char *);
extern int vf_restart16_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN vf_restart16\n");
if(vf_restart16_main()){replay_text("BOARD_CASE_FAIL vf_restart16\n");return 1;}
replay_text("BOARD_CASE_PASS vf_restart16\nBOARD_REPLAY_PASS\n");return 0;}
