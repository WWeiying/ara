extern void replay_text(const char *);
extern int tail_snan_lt_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN tail_snan_lt\n");
if(tail_snan_lt_main()){replay_text("BOARD_CASE_FAIL tail_snan_lt\n");return 1;}
replay_text("BOARD_CASE_PASS tail_snan_lt\nBOARD_REPLAY_PASS\n");return 0;}
