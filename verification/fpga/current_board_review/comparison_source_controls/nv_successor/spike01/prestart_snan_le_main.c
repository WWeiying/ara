extern void replay_text(const char *);
extern int prestart_snan_le_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN prestart_snan_le\n");
if(prestart_snan_le_main()){replay_text("BOARD_CASE_FAIL prestart_snan_le\n");return 1;}
replay_text("BOARD_CASE_PASS prestart_snan_le\nBOARD_REPLAY_PASS\n");return 0;}
