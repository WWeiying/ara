extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int rvv_small_fp_move_restart_e16_mf4_ops2_main(void);
int main(void) { unsigned long vlenb; __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case=1;
replay_text("BOARD_CASE_BEGIN rvv_small_fp_move_restart_e16_mf4_ops2\n");
int rc=rvv_small_fp_move_restart_e16_mf4_ops2_main();
if(rc) { replay_text("BOARD_CASE_FAIL rvv_small_fp_move_restart_e16_mf4_ops2\n"); return rc; }
replay_text("BOARD_CASE_PASS rvv_small_fp_move_restart_e16_mf4_ops2\nBOARD_REPLAY_PASS\n"); return 0;
}
