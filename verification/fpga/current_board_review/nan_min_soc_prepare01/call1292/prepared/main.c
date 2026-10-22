extern int nan_min_call1292_main(void);
extern void replay_text(const char *);
int main(void) {
 unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));
 if(n!=128) {replay_text("BOARD_VLEN_FAIL\n"); return 2;}
 replay_text("BOARD_CASE_BEGIN nan_min_call1292\n");
 int status=nan_min_call1292_main();
 if(status) {replay_text("BOARD_CASE_FAIL nan_min_call1292\n"); return status;}
 replay_text("BOARD_CASE_PASS nan_min_call1292\nBOARD_REPLAY_PASS\n"); return 0;
}
