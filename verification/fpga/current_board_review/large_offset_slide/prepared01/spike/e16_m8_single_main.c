extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int e16_m8_single_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 5;
replay_text("BOARD_CASE_BEGIN e16_m8_single\n");
if (e16_m8_single_main()) { replay_text("BOARD_CASE_FAIL e16_m8_single\n"); return 5; }
replay_text("BOARD_CASE_PASS e16_m8_single\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
