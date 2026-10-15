extern int arithmetic_main(void);
extern void replay_text(const char *);
int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
if(n!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
replay_text("BOARD_CASE_BEGIN rvv_matrix_e8_mf4\n");
int r=arithmetic_main();
if(r){replay_text("BOARD_CASE_FAIL rvv_matrix_e8_mf4\n");return r;}
replay_text("ARITHMETIC_FULL_PASS rvv_matrix_e8_mf4\nBOARD_REPLAY_PASS\n");return 0;}
