extern void replay_text(const char *);
extern int smoke_e64_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN smoke_e64\n");
if(smoke_e64_main()){replay_text("BOARD_CASE_FAIL smoke_e64\n");return 1;}
replay_text("BOARD_CASE_PASS smoke_e64\nBOARD_REPLAY_PASS\n");return 0;}
