extern void replay_text(const char *);
extern int matrix_e16_main(void);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){return 90;}
replay_text("BOARD_CASE_BEGIN matrix_e16\n");
if(matrix_e16_main()){replay_text("BOARD_CASE_FAIL matrix_e16\n");return 1;}
replay_text("BOARD_CASE_PASS matrix_e16\nBOARD_REPLAY_PASS\n");return 0;}
