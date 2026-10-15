extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int e8_m4_single_main(void);
extern int e8_m4_sequence_main(void);
extern int e8_m8_single_main(void);
extern int e8_m8_sequence_main(void);
extern int e16_m8_single_main(void);
extern int e16_m8_sequence_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN e8_m4_single\n");
if (e8_m4_single_main()) { replay_text("BOARD_CASE_FAIL e8_m4_single\n"); return 1; }
replay_text("BOARD_CASE_PASS e8_m4_single\n");
replay_case = 2;
replay_text("BOARD_CASE_BEGIN e8_m4_sequence\n");
if (e8_m4_sequence_main()) { replay_text("BOARD_CASE_FAIL e8_m4_sequence\n"); return 2; }
replay_text("BOARD_CASE_PASS e8_m4_sequence\n");
replay_case = 3;
replay_text("BOARD_CASE_BEGIN e8_m8_single\n");
if (e8_m8_single_main()) { replay_text("BOARD_CASE_FAIL e8_m8_single\n"); return 3; }
replay_text("BOARD_CASE_PASS e8_m8_single\n");
replay_case = 4;
replay_text("BOARD_CASE_BEGIN e8_m8_sequence\n");
if (e8_m8_sequence_main()) { replay_text("BOARD_CASE_FAIL e8_m8_sequence\n"); return 4; }
replay_text("BOARD_CASE_PASS e8_m8_sequence\n");
replay_case = 5;
replay_text("BOARD_CASE_BEGIN e16_m8_single\n");
if (e16_m8_single_main()) { replay_text("BOARD_CASE_FAIL e16_m8_single\n"); return 5; }
replay_text("BOARD_CASE_PASS e16_m8_single\n");
replay_case = 6;
replay_text("BOARD_CASE_BEGIN e16_m8_sequence\n");
if (e16_m8_sequence_main()) { replay_text("BOARD_CASE_FAIL e16_m8_sequence\n"); return 6; }
replay_text("BOARD_CASE_PASS e16_m8_sequence\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
