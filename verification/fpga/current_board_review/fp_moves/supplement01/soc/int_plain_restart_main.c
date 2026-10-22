extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int int_plain_restart_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN int_plain_restart\n");
if (int_plain_restart_main()) { replay_text("BOARD_CASE_FAIL int_plain_restart\n"); return 1; }
replay_text("BOARD_CASE_PASS int_plain_restart\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
