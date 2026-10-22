extern void replay_text(const char *);
extern int no_snan_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN no_snan\n");
if(no_snan_main()){replay_text("BOARD_CASE_FAIL no_snan\n");return 1;}
replay_text("BOARD_CASE_PASS no_snan\nBOARD_REPLAY_PASS\n");return 0;}
