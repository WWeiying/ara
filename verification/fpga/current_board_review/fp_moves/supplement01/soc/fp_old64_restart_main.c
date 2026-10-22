extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int fp_old64_restart_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 3;
replay_text("BOARD_CASE_BEGIN fp_old64_restart\n");
if (fp_old64_restart_main()) { replay_text("BOARD_CASE_FAIL fp_old64_restart\n"); return 3; }
replay_text("BOARD_CASE_PASS fp_old64_restart\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
