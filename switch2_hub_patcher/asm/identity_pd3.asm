; EXPERIMENTAL PD3 identity-response diagnostic, based on v4.
; Reached via JMP from251F after the original identity admission checks and
; SVID/command/ACK setup. No added call frame, RAM or direct hardware access.
; PD3: exact captured official response body. PD2: replay original instructions.
; Uses original5876 header builder (including its existing clear/IRQ limits).
; Payload copy uses bank0R0, not ISR-shared67, to avoid counter-overrun races.
; USB metadata/descriptors, power policy, DP, Nintendo replies remain unchanged.
.module identity_pd3
.area IDENTITY_PD3 (ABS,CODE)
.org 0x7c40
identity_ack:
    jnb 0x03,identity_legacy
    mov r7,#6
    lcall 0x5876
    mov r0,#0
identity_copy:
    mov dptr,#0x7d00
    mov a,r0
    movc a,@a+dptr
    mov r7,a
    mov a,r0
    add a,#0x26
    mov dpl,a
    clr a
    addc a,#0x10
    mov dph,a
    mov a,r7
    movx @dptr,a
    inc r0
    cjne r0,#20,identity_copy
    ljmp 0x2579             ; original RX arbitration / TX trigger / wait state
identity_legacy:
    mov r7,#5
    lcall 0x5876
    ljmp 0x2524             ; original table copy and v4 VID-read redirects

.org 0x7d00
identity_body:
    ; IDHeader5460057E, Cert0, Product20620000, UFP65000031, trailing0.
    .db 0x7e,0x05,0x60,0x54, 0,0,0,0, 0,0,0x62,0x20
    .db 0x31,0,0,0x65, 0,0,0,0
