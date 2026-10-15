extern int original_e32_m2_main(void);
extern void replay_text(const char *);
int main(void) {
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {replay_text("BOARD_VLEN_FAIL\n"); return 2;}
 replay_text("BOARD_CASE_BEGIN original_e32_m2\n");
 int status=original_e32_m2_main();
 if(status) {replay_text("BOARD_CASE_FAIL original_e32_m2\n"); return status;}
 replay_text("BOARD_CASE_PASS original_e32_m2\nBOARD_REPLAY_PASS\n"); return 0;
}
