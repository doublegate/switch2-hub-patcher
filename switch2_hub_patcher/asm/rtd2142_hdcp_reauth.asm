; RTD2142 bank 4, HDMI TX HDCP 2.2. CANDIDATE (SDR-fix v7b), tested on one hub.
;
; Stock behaviour: after an output restart (for example a Mac HDR -> SDR switch) the HDCP
; 2.2 transmitter state machine (state in D943[3:0], set by hdmitx_ram_fafc, which also sets
; D943 bit 4 "state changed") authenticates the TV again while the TV is still locking to
; the new signal. On some restarts the TV's cipher ends up out of step: black picture, mode
; banners cycling at random, for ever. The TV never sets REAUTH_REQ, so the 200 ms RxStatus
; poll in state 10 (hdmitx_ram_507e -> ebec) never re-authenticates. On a hub, moving the
; state machine from 10 (authenticated) to 1 (start) by hand recovered the TV every time.
;
; This overlay does that once per authentication the firmware starts, about 2 s after it
; first reaches state 10. HDCP stays on; the only gap is the firmware's own
; re-authentication. One XDATA byte (E9F0, unreferenced by the stock firmware, 0 at
; power-up): bit 7 = done for this authentication, bit 6 = our re-authentication is in
; progress, [3:0] = 200 ms ticks counted in state 10. Bit 6 is cleared only when state 10 is
; reached again: the first attempt after the forced state 1 usually fails and the firmware
; retries through state 1 (E0DE + 1), which must not re-arm (v7 looped that way).
;
; Hooks (checked by patch_rtd2142_sdr_fix.py):
;   5098  lcall ebec (state 10 tick: RxStatus poll)  ->  ljmp hdcp_reauth_tick
;   4dc5  lcall f3e0 (state 1 entry)                 ->  ljmp hdcp_auth_start

.module rtd2142_hdcp_reauth
.area HDCPREAUTH (ABS,CODE)
.org 0xff00

REAUTH_FLAG = 0xe9f0
HDCP22_STATE = 0xd943
TICKS = 10                  ; 10 x 200 ms in state 10 before the one re-authentication

hdcp_reauth_tick::
    mov dptr,#REAUTH_FLAG
    movx a,@dptr
    jnb acc.7,reauth_count
    jnb acc.6,reauth_poll   ; done for this authentication
    anl a,#0x80             ; our re-authentication (retries included) reached state 10
    movx @dptr,a
    sjmp reauth_poll
reauth_count:
    inc a
    movx @dptr,a
    anl a,#0x0f
    cjne a,#TICKS,reauth_poll
    mov a,#0xc0             ; done, and the next authentication is ours
    movx @dptr,a
    mov dptr,#HDCP22_STATE
    movx a,@dptr
    anl a,#0xf0
    orl a,#0x11             ; state 1 + state changed, as hdmitx_ram_fafc(1) writes it
    movx @dptr,a
    mov r7,#0               ; no RxStatus this tick (stock: CJNE R7,#8 then falls through)
    ljmp 0x509b
reauth_poll:
    lcall 0xebec            ; stock: RxStatus poll, result in R7
    ljmp 0x509b

hdcp_auth_start::
    mov dptr,#REAUTH_FLAG
    movx a,@dptr
    jb acc.6,auth_keep      ; ours, or the firmware retrying ours after a failed attempt
    clr a                   ; an authentication the firmware started: arm the re-authentication
    movx @dptr,a
auth_keep:
    lcall 0xf3e0            ; stock: read HDCP2Version
    ljmp 0x4dc8
