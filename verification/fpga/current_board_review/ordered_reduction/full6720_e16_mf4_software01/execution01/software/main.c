extern int fp_redspecial_e16_mf4_full6720_main(void);
extern void replay_text(const char *);
int main(void) {
 replay_text("BOARD_CASE_BEGIN fp_redspecial_e16_mf4_full6720\n");
 int rc=fp_redspecial_e16_mf4_full6720_main();
 if(rc) { replay_text("BOARD_CASE_FAIL fp_redspecial_e16_mf4_full6720\n"); return rc; }
 replay_text("BOARD_CASE_PASS fp_redspecial_e16_mf4_full6720\nBOARD_REPLAY_PASS\n"); return 0;
}
