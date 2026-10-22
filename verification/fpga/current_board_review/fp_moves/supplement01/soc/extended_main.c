extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int int_plain_restart_main(void);
extern int int_plain_start0_main(void);
extern int fp_old64_restart_main(void);
extern int fp_old64_start0_main(void);
extern int fp_old64_empty_main(void);
extern int int_old8_restart_main(void);
extern int int_old8_start0_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN int_plain_restart\n");
if (int_plain_restart_main()) { replay_text("BOARD_CASE_FAIL int_plain_restart\n"); return 1; }
replay_text("BOARD_CASE_PASS int_plain_restart\n");
replay_case = 2;
replay_text("BOARD_CASE_BEGIN int_plain_start0\n");
if (int_plain_start0_main()) { replay_text("BOARD_CASE_FAIL int_plain_start0\n"); return 2; }
replay_text("BOARD_CASE_PASS int_plain_start0\n");
replay_case = 3;
replay_text("BOARD_CASE_BEGIN fp_old64_restart\n");
if (fp_old64_restart_main()) { replay_text("BOARD_CASE_FAIL fp_old64_restart\n"); return 3; }
replay_text("BOARD_CASE_PASS fp_old64_restart\n");
replay_case = 4;
replay_text("BOARD_CASE_BEGIN fp_old64_start0\n");
if (fp_old64_start0_main()) { replay_text("BOARD_CASE_FAIL fp_old64_start0\n"); return 4; }
replay_text("BOARD_CASE_PASS fp_old64_start0\n");
replay_case = 5;
replay_text("BOARD_CASE_BEGIN fp_old64_empty\n");
if (fp_old64_empty_main()) { replay_text("BOARD_CASE_FAIL fp_old64_empty\n"); return 5; }
replay_text("BOARD_CASE_PASS fp_old64_empty\n");
replay_case = 6;
replay_text("BOARD_CASE_BEGIN int_old8_restart\n");
if (int_old8_restart_main()) { replay_text("BOARD_CASE_FAIL int_old8_restart\n"); return 6; }
replay_text("BOARD_CASE_PASS int_old8_restart\n");
replay_case = 7;
replay_text("BOARD_CASE_BEGIN int_old8_start0\n");
if (int_old8_start0_main()) { replay_text("BOARD_CASE_FAIL int_old8_start0\n"); return 7; }
replay_text("BOARD_CASE_PASS int_old8_start0\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
