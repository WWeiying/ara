extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int int_old8_restart_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 6;
replay_text("BOARD_CASE_BEGIN int_old8_restart\n");
if (int_old8_restart_main()) { replay_text("BOARD_CASE_FAIL int_old8_restart\n"); return 6; }
replay_text("BOARD_CASE_PASS int_old8_restart\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
