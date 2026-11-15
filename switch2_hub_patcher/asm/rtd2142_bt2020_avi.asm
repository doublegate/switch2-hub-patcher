; RTD2142 bank 2, HDMI AVI InfoFrame: BT.2020 for HDR when the source does not say so.
; CANDIDATE (BT.2020 rework v1, stacked on SDR-fix v7b), not yet tested on a hub.
;
; Why: over DisplayPort a source can only signal BT.2020 in the VSC SDP (MSA MISC1 bit 6).
; A source that sends HDR metadata (PQ/HLG) but leaves its colorimetry in MISC0 (the
; Switch 2, as far as is known) gets an AVI saying BT.709 or "no data", so HDR looks
; washed out. The stock AVI builder (hdmi_avi_fill_fields, 7D03) already maps a VSC
; colorimetry code to C/EC correctly (BT.2020 RGB = code 6, BT.2020 YCbCr = code 0x0E,
; both EC = 6), so the Mac, which uses the VSC SDP, needs nothing.
;
; What this does differently from the upstream BT.2020 patch (rtd2142_hdr_avi.asm):
; - An AVI the builder already marked extended (C = 3, any EC, including the version-4
;   EC = 7 form with ACE in PB14) is left exactly as built.
; - BT.2020 is claimed only when the sink lists it for the encoding being sent: the
;   Colorimetry Data Block (CTA-861 extended tag 5) bit BT2020_RGB for RGB output, bit
;   BT2020_YCC for YCbCr 4:4:4 / 4:2:2 / 4:2:0 output. No block, a malformed CTA block,
;   or no EDID (the extension's tag is not 02): nothing is claimed. The hub keeps the sink's EDID (base block and first
;   extension) in XDATA C600..C6FF (EDID buffer of logical port 1, the HDMI connector,
;   selected by edid_buffer_load_q in bank 0 CEAF), so no DDC read is needed.
; - The decision is re-made on every hdmi_drm_update pass, not only when the HDR packet
;   enable changes, because an output restart builds the AVI before the new HDR metadata
;   is current. The AVI is rebuilt only when the decision changes.
; Pixel data, CSC, quantization range (Q) and every other AVI field are unchanged.
;
; State: one XDATA byte, E9F1 (unreferenced by the stock firmware; C500..FCFF is cleared
; at power-up by the startup code): bit 0 = the last AVI was marked BT.2020 by this code,
; bit 1 = the last AVI was already extended colorimetry as built (leave it alone).
;
; Hooks (checked by patch_rtd2142_bt2020.py, on the SDR-fix v7b image):
;   F390  lcall b9f6 (hdmi_build_avi)                 ->  lcall avi_wrap
;   F31F  ljmp ff20 (v7b hdmi_drm_enable_guard)       ->  ljmp drm_on
;   F326  lcall 4ae7 (HDR packet off; movx, ret)      ->  ljmp drm_off
;
; Overlay FF36..FFFD (200 bytes), just above v7b's hdmi_drm_enable_guard (FF20..FF34): the
; last free space in bank 2. Registers: A, C, DPTR, R2..R7. Every caller tolerates that:
; hdmi_build_avi itself leaves R1..R7 undefined and hdmi_pkt_commit (F8D5) reloads all it
; uses; the hdmi_drm_update paths end in a ret, and the stock one already calls F36F.

.module rtd2142_bt2020_avi
.area BT2020AVI (ABS,CODE)
.org 0xff36

FLAG = 0xe9f1
EDID = 0xc600               ; sink EDID, 256 bytes (base block + first extension)

avi_wrap::                  ; replaces "lcall 0xb9f6" at F390
    lcall 0xb9f6            ; stock: build the AVI into 5B44.. (PB1 5B4A, PB2 5B49, PB3 5B48)
    mov dptr,#0x5b49        ; PB2 as built: C in bits 7:6
    movx a,@dptr
    anl a,#0xc0
    cjne a,#0xc0,aw_plain
    mov a,#0x02             ; already extended colorimetry: leave the AVI as built
    sjmp aw_flag
aw_plain:
    acall want_bt2020
    clr a
    rlc a                   ; 1 = mark this AVI BT.2020
aw_flag:
    mov dptr,#FLAG
    movx @dptr,a
    cjne a,#0x01,aw_done
    mov dptr,#0x5b49        ; PB2: C = 3 (extended)
    movx a,@dptr
    mov r6,a
    orl a,#0xc0
    movx @dptr,a
    clr c
    subb a,r6
    mov r7,a                ; byte-sum change so far
    mov dptr,#0x5b48        ; PB3: EC (bits 6:4) = 6, BT.2020 R'G'B' or Y'C'bC'r
    movx a,@dptr
    mov r6,a
    anl a,#0x8f
    orl a,#0x60
    movx @dptr,a
    clr c
    subb a,r6
    add a,r7
    mov r7,a
    mov dptr,#0x5b4b        ; checksum: header + payload still sum to 0
    movx a,@dptr
    clr c
    subb a,r7
    movx @dptr,a
aw_done:
    ret

drm_on::                    ; replaces "ljmp 0xff20" at F31F (metadata present)
    lcall 0xff20            ; v7b hdmi_drm_enable_guard: HDR packet on only for EOTF != 0
    sjmp recheck
drm_off::                   ; replaces "lcall 0x4ae7" at F326 (no metadata)
    lcall 0x4ae7            ; stock: DPTR = 5B6B, A = 5B6B & DF
    movx @dptr,a            ; stock: HDR packet off
recheck:                    ; rebuild the AVI when the BT.2020 decision changed
    mov dptr,#FLAG
    movx a,@dptr
    jb acc.1,rc_done        ; built extended: the source's colorimetry stands
    mov r2,a                ; 1 = the current AVI is marked BT.2020
    acall want_bt2020
    clr a
    rlc a
    xrl a,r2
    jz rc_done
    clr 0x02                ; same call the output start uses (CD19)
    clr a
    mov r5,a                ; builder 0: AVI
    mov r7,a
    mov r6,a
    ljmp 0xf36f             ; hdmi_pkt_build; its ret returns to our caller
rc_done:
    ret

want_bt2020:                ; C = 1: HDR (PQ/HLG) and the sink lists BT.2020 for the encoding
    mov dptr,#0xe362        ; logical port 1 HDR status: bit 1 = metadata present
    movx a,@dptr
    jnb acc.1,w_no
    mov dptr,#0xdd9f        ; rx_drm_eotf_p1: [2:0] EOTF, 2 = PQ, 3 = HLG
    movx a,@dptr
    anl a,#0x06
    cjne a,#0x02,w_no
    acall sink_colorimetry  ; A = Colorimetry Data Block byte 3, 0 if none
    mov r7,a
    mov dptr,#0xe0e6        ; HDMI output pixel encoding (AVI Y): 0 RGB, 1 422, 2 444, 3 420
    movx a,@dptr
    anl a,#0x07
    jnz w_ycc
    mov a,r7
    mov c,acc.7             ; BT2020_RGB
    ret
w_ycc:
    jb acc.2,w_no           ; 4..7: reserved encoding
    mov a,r7
    mov c,acc.6             ; BT2020_YCC
    ret
w_no:
    clr c
    ret

sink_colorimetry:           ; A = byte 3 of the sink's Colorimetry Data Block, or 0
    mov dptr,#EDID+0x80     ; CTA-861 extension: tag 02
    movx a,@dptr
    cjne a,#0x02,sc_none
    inc dptr
    inc dptr                ; d: first DTD offset; data blocks are at 4 .. d-1
    movx a,@dptr
    jb acc.7,sc_none        ; d > 127: malformed
    mov r6,a
    mov r5,#0x04            ; offset of the next data block header
sc_loop:
    mov a,r5
    clr c
    subb a,r6
    jnc sc_none             ; reached d: no Colorimetry Data Block
    mov a,r5
    orl a,#0x80
    mov dpl,a
    mov dph,#0xc6           ; EDID page
    movx a,@dptr            ; header: tag [7:5], length [4:0]
    mov r4,a
    anl a,#0x1f
    mov r3,a
    add a,r5
    clr c
    subb a,r6
    jnc sc_none             ; block runs past d: malformed, stop
    mov a,r4
    anl a,#0xe0
    cjne a,#0xe0,sc_next    ; tag 7: extended tag follows
    mov a,r3
    add a,#0xfe
    jnc sc_next             ; length < 2: too short for a Colorimetry Data Block
    inc dptr
    movx a,@dptr
    cjne a,#0x05,sc_next    ; extended tag 5: Colorimetry Data Block
    inc dptr
    movx a,@dptr            ; BT2020_RGB bit 7, BT2020_YCC bit 6, BT2020_cYCC bit 5, ...
    ret
sc_next:
    mov a,r5
    add a,r3
    inc a
    mov r5,a
    sjmp sc_loop
sc_none:
    clr a
    ret
