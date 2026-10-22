extern void replay_text(const char *);
extern int smoke_e32_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN smoke_e32\n");
if(smoke_e32_main()){replay_text("BOARD_CASE_FAIL smoke_e32\n");return 1;}
replay_text("BOARD_CASE_PASS smoke_e32\nBOARD_REPLAY_PASS\n");return 0;}
