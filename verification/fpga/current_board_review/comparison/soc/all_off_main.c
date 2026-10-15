extern void replay_text(const char *);
extern int all_off_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN all_off\n");
if(all_off_main()){replay_text("BOARD_CASE_FAIL all_off\n");return 1;}
replay_text("BOARD_CASE_PASS all_off\nBOARD_REPLAY_PASS\n");return 0;}
