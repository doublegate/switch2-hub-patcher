; RTD2142 bank 2, HDMI 5Bxx engine (logical port 1 = HDMI connector).
; UNVERIFIED offline candidate: "PQ/HLG metadata implies BT.2020" for the AVI
; InfoFrame, in the spirit of third-party "switch2 color space patch" firmware.
;
; Hooks (all bank 2, original bytes checked by tools/patch_rtd2142_hdr_avi.py):
;   F390  lcall 0xb9f6 -> lcall avi_wrap     (every AVI build goes through here)
;   F31F  HDR packet enable  -> ljmp hdr_enable  (rebuild AVI on off->on)
;   F326  HDR packet disable -> ljmp hdr_disable (rebuild AVI on on->off)
;
; Condition: source metadata present (E362 bit1, logical port 1) and the cached
; HDR SDP EOTF (DD9F & 7) is PQ (2) or HLG (3). Then AVI C=3 and EC=6
; (BT.2020 RGB / YCbCr) are written into the staged packet and its checksum is
; corrected. No pixel processing, CSC or cache state is changed.
; No new RAM; uses A, B-free registers R5..R7, DPTR and carry only.

.module rtd2142_hdr_avi
.area HDRAVI (ABS,CODE)
.org 0xff80

hdr_active:                 ; C=1 when HDR (PQ/HLG) metadata is present
    mov dptr,#0xe362
    movx a,@dptr
    jnb acc.1,hdr_inactive
    mov dptr,#0xdd9f
    movx a,@dptr
    anl a,#0x07
    cjne a,#0x02,hdr_check_hlg
    setb c
    ret
hdr_check_hlg:
    cjne a,#0x03,hdr_inactive
    setb c
    ret
hdr_inactive:
    clr c
    ret

avi_wrap::                   ; replaces "lcall 0xb9f6" in F36F
    lcall 0xb9f6
    acall hdr_active
    jnc avi_done
    mov dptr,#0x5b49        ; PB2: C in bits 7:6 -> 3 (extended)
    movx a,@dptr
    mov r6,a
    orl a,#0xc0
    movx @dptr,a
    clr c
    subb a,r6
    mov r7,a                ; delta from PB2
    mov dptr,#0x5b48        ; PB3: EC in bits 6:4 -> 6 (BT.2020)
    movx a,@dptr
    mov r6,a
    anl a,#0x8f
    orl a,#0x60
    movx @dptr,a
    clr c
    subb a,r6
    add a,r7                ; total byte-sum change
    mov r7,a
    mov dptr,#0x5b4b        ; checksum: keep header+payload sum == 0
    movx a,@dptr
    clr c
    subb a,r7
    movx @dptr,a
avi_done:
    ret

hdr_enable::                 ; replaces F31F: 5B6B |= 0x20
    mov dptr,#0x5b6b
    movx a,@dptr
    jb acc.5,enable_done
    orl a,#0x20
    movx @dptr,a
    sjmp rebuild_avi
enable_done:
    ret

hdr_disable::                ; replaces F326: 5B6B &= ~0x20
    mov dptr,#0x5b6b
    movx a,@dptr
    jnb acc.5,disable_quiet
    anl a,#0xdf
    movx @dptr,a
    sjmp rebuild_avi
disable_quiet:
    anl a,#0xdf
    movx @dptr,a
    ret

rebuild_avi:                ; same call the original init path uses (CD19)
    clr 0x02
    clr a
    mov r5,a
    mov r7,a
    mov r6,a
    ljmp 0xf36f
