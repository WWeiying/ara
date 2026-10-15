extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int fp_move_original_main(void);
extern int fp_move_start0_main(void);
extern int fp_move_start_eq_vl_main(void);
extern int fp_move_vl0_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN fp_move_original\n");
if (fp_move_original_main()) { replay_text("BOARD_CASE_FAIL fp_move_original\n"); return 1; }
replay_text("BOARD_CASE_PASS fp_move_original\n");
replay_case = 2;
replay_text("BOARD_CASE_BEGIN fp_move_start0\n");
if (fp_move_start0_main()) { replay_text("BOARD_CASE_FAIL fp_move_start0\n"); return 2; }
replay_text("BOARD_CASE_PASS fp_move_start0\n");
replay_case = 3;
replay_text("BOARD_CASE_BEGIN fp_move_start_eq_vl\n");
if (fp_move_start_eq_vl_main()) { replay_text("BOARD_CASE_FAIL fp_move_start_eq_vl\n"); return 3; }
replay_text("BOARD_CASE_PASS fp_move_start_eq_vl\n");
replay_case = 4;
replay_text("BOARD_CASE_BEGIN fp_move_vl0\n");
if (fp_move_vl0_main()) { replay_text("BOARD_CASE_FAIL fp_move_vl0\n"); return 4; }
replay_text("BOARD_CASE_PASS fp_move_vl0\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
