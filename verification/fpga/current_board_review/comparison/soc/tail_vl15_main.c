extern void replay_text(const char *);
extern int tail_vl15_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN tail_vl15\n");
if(tail_vl15_main()){replay_text("BOARD_CASE_FAIL tail_vl15\n");return 1;}
replay_text("BOARD_CASE_PASS tail_vl15\nBOARD_REPLAY_PASS\n");return 0;}
