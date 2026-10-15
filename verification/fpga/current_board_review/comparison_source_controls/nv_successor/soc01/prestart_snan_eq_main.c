extern void replay_text(const char *);
extern int prestart_snan_eq_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN prestart_snan_eq\n");
if(prestart_snan_eq_main()){replay_text("BOARD_CASE_FAIL prestart_snan_eq\n");return 1;}
replay_text("BOARD_CASE_PASS prestart_snan_eq\nBOARD_REPLAY_PASS\n");return 0;}
