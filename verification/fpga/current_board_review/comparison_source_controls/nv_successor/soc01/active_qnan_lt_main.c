extern void replay_text(const char *);
extern int active_qnan_lt_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN active_qnan_lt\n");
if(active_qnan_lt_main()){replay_text("BOARD_CASE_FAIL active_qnan_lt\n");return 1;}
replay_text("BOARD_CASE_PASS active_qnan_lt\nBOARD_REPLAY_PASS\n");return 0;}
