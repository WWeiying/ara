extern int nan_minmax_call1234_main(void);
extern void replay_text(const char *);
int main(void) {
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {replay_text("BOARD_VLEN_FAIL\n"); return 2;}
 replay_text("BOARD_CASE_BEGIN nan_minmax_call1234\n");
 int status=nan_minmax_call1234_main();
 if(status) {replay_text("BOARD_CASE_FAIL nan_minmax_call1234\n"); return status;}
 replay_text("BOARD_CASE_PASS nan_minmax_call1234\nBOARD_REPLAY_PASS\n"); return 0;
}
