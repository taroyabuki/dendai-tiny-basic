CPU 6800
*=$0100

MON_0013 equ $0013
MON_0014 equ $0014
MON_0015 equ $0015
MON_00B8 equ $00B8
MON_8004 equ $8004
MON_E1AC equ $E1AC
MON_E1D1 equ $E1D1

ENTRY jsr L01B3
 jmp L01CB
L0106 bsr L0170
 cmpa #$02
 bne L0106
 bra L012C
L010E ldaa $12
 bne L0106
 ldaa $13
 beq L0127
 ldaa #$0A
 clrb
 ldx #$0008
 jsr L0493
 jsr L0401
 jsr L07EA
 bra L012F
L0127 ldaa #$23
 jsr L043F
L012C ldx #$0030
L012F eora $06
 staa $06
 bsr L0170
 cmpa #$0D
 bne L0148
 clr $00,x
 stx $10
 ldaa $12
 bne L0144
L0141 jsr L083C
L0144 ldx #$0030
 rts
L0148 cmpa #$18
 bne L0150
 bsr L0141
 bra L012F
L0150 cmpa #$0F
 bne L0161
 ldaa #$5F
 jsr L043F
 cpx #$0030
 beq L012F
 dex
 bra L012F
L0161 cpx #$0076
 beq L016B
 staa $00,x
 inx
 bra L012F
L016B ldab #$64
 jmp L0859
L0170 jsr L0940
 anda #$7F
 beq L0170
 cmpa #$7F
 beq L0170
 cmpa #$03
 bne L018A
 bra L01CB
L0181 psha
 ldaa MON_8004
 bmi L0189
 bsr L0170
L0189 pula
L018A rts
L018B ldx $B6
 tpa
 staa $00,x
 inx
 staa $00,x
 stx $B8
 rts
 db $8D,$F3,$97,$12,$20,$40,$07,$97
 db $13,$BD,$09,$50,$80,$0A,$C2,$00
L01A6 staa $09
 stab $08
 rts
 db $BD,$03,$2C,$BD,$06,$7B,$20,$1D
L01B3 ldx #$0980
 stx $B6
 ldaa #$AA
L01BA inx
 ldab $01,x
 staa $01,x
 ldaa $01,x
 stab $01,x
 cmpa #$AA
 beq L01BA
 stx $BA
 bsr L018B
L01CB lds #$A047
 bsr L024F
L01D0 jsr L083C
 ldx #READY_MSG
 jsr L0853
 tpa
 staa $0E
L01DC lds #$A047
 jsr L010E
 jsr L04FD
 bcc L0264
 bsr L01A6
 bsr L01ED
 bra L01DC
L01ED stx $0A
 sts $0C
 bsr L022A
 stx $04
 bcs L0209
 bsr L026B
 inx
 txs
 ldx $04
L01FD aslb
 pulb
 stab $00,x
 inx
 bpl L01FD
 bcc L01FD
 dex
 stx $B8
L0209 ldx $0A
 ldaa $00,x
 beq L024C
 ldaa $11
 suba $0B
 adda #$03
 ldx $B8
 adda $B9
 staa $B9
 bcc L0220
 inc MON_00B8
L0220 bsr L029F
 bcc L0233
 stx $B8
 ldab #$6E
 bra L0289
L022A ldaa $12
 beq L027A
 ldx $B8
 dex
 sec
 rts
L0233 lds $B8
 inx
L0236 dex
 ldaa $00,x
 psha
 cpx $04
 bne L0236
 lds $08
 sts $00,x
 inx
 lds $0A
 des
L0246 inx
 pula
 staa $00,x
 bne L0246
L024C lds $0C
 rts
L024F ldx #$0000
 stx $12
 ldx #ENTRY
 stx $BE
 ldx #$A080
 stx $BC
 ldx #$0080
 stx $80
 rts
L0264 stx $0A
 ldx #L087C
 bra L02C2
L026B inx
L026C inx
 tst $00,x
 bne L026C
 rts
 db $DE,$0E,$2B,$04,$8D,$04,$24,$19
L027A ldx $B6
 ldaa $09
 ldab $08
 bmi L0287
 bne L028F
 tsta
 bne L028F
L0287 ldab #$78
L0289 jmp L0859
L028C bsr L026B
 inx
L028F bsr L02FC
 bhi L028C
 rts
 db $BD,$06,$9E,$5D,$26,$20,$4D,$27
 db $D0,$20,$1B
L029F ldaa $BB
 ldab $BA
 suba $B9
 sbcb $B8
 rts
L02A8 jmp L01D0
 db $8D,$A2,$DE,$B6
L02AF stx $DE
 ldaa $00,x
 asla
 ldaa $0E
 bls L02A8
 inx
 inx
L02BA jsr L0181
 stx $0A
 ldx #L089C
L02C2 lds #$A047
 jsr L0577
L02C8 jsr L0456
 bne L02C8
 inx
 bcc L02AF
 bra L02BA
 db $5F,$D7,$04,$8D,$16,$24,$C6,$49
 db $48,$48,$48,$48,$79,$00,$04,$59
 db $48,$26,$F9,$08,$8D,$05,$25,$EF
 db $96,$04,$39,$BD,$05,$25,$25,$09
 db $80,$07,$81,$3A,$0C,$2D,$02,$81
 db $40,$39
L02FC cmpb $00,x
 bne L0302
 cmpa $01,x
L0302 rts
 db $DF,$0A,$CE,$09,$0C
L0308 sts $0C
L030A lds $0A
 des
 inx
L030E inx
L030F pula
 cmpa #$20
 beq L030F
 suba $00,x
 asla
 bne L0322
 bcc L030E
 inx
 ins
 sts $0A
L031F lds $0C
 rts
L0322 ldaa $00,x
 inx
 bpl L0322
 coma
 bne L030A
 bra L031F
 db $8D,$22,$27,$23,$8D,$40,$27,$08
 db $DF,$0A,$CE,$09,$16,$BD,$05,$77
 db $8D,$12,$27,$13,$81,$3B,$27,$06
 db $81,$2C,$26,$49,$8D,$0F,$08,$8D
 db $03,$26,$E1,$39,$7E,$04,$56,$7E
 db $08,$3C,$BD,$07,$EA,$96,$14,$85
 db $07,$26,$F7,$39,$8D,$29,$7E,$04
 db $3F,$8D,$24,$16,$20,$03,$BD,$07
 db $EA,$D1,$14,$22,$F9,$39,$8D,$DC
 db $81,$22,$27,$04,$81,$27,$26,$0E
 db $16,$08,$20,$02,$8D,$E0,$A6,$00
 db $27,$0B,$08,$11,$26,$F6,$39,$BD
 db $05,$B8,$7E,$06,$A0,$C6,$82,$20
 db $02,$C6,$8C,$7E,$08,$59,$A6,$00
 db $AA,$01,$27,$F5,$8D,$40,$8D,$2C
 db $49,$40,$16,$8D,$2C,$49,$88,$01
 db $46,$8D,$1C,$BD,$02,$FC,$26,$08
 db $4F,$16,$6C,$03,$26,$02,$6C,$02
 db $08,$08,$39
L03BF bsr L03E2
L03C1 bsr L03D0
 rola
 rolb
 suba $01,x
 sbcb $00,x
 bsr L03D5
 dec MON_0015
 bne L03C1
L03D0 rol $03,x
 rol $02,x
 rts
L03D5 pshb
 eorb $00,x
 pulb
 sec
 bpl L03E1
 adda $01,x
 adcb $00,x
 clc
L03E1 rts
L03E2 ldaa #$10
 staa $15
 clra
 tab
 rts
 db $8D,$F7,$48,$59,$69,$01,$69,$00
 db $24,$04,$AB,$03,$E9,$02,$7A,$00
 db $15,$26,$EF,$08,$08,$7E,$04,$97
L0401 ldx $00,x
 stx $02
 ldx #$0002
 bsr L0448
 bcc L0410
 ldaa #$2D
 bsr L043F
L0410 dex
 dex
 ldab #$0A
 stab $01,x
 clr $00,x
 asrb
L0419 pshb
 bsr L03BF
 pulb
 psha
 decb
 bne L0419
 ldx #$0030
 ldab #$04
L0426 ldaa $15
 pula
 bne L042F
 staa $15
 beq L0431
L042F bsr L0435
L0431 decb
 bne L0426
 pula
L0435 adda #$30
 tst MON_0013
 beq L043F
 staa $00,x
 inx
L043F inc MON_0014
 jsr L0181
 jmp MON_E1D1
L0448 tst $00,x
 bpl L0454
 neg $01,x
 bne L0452
 dec $00,x
L0452 com $00,x
L0454 rts
L0455 inx
L0456 ldaa $00,x
 cmpa #$20
 beq L0455
 tsta
 beq L0462
 cmpa #$3A
 sec
L0462 rts
 db $8D,$F1,$81,$2D,$26,$04,$8D,$1F
 db $20,$07,$81,$2B,$27,$01,$09,$8D
 db $5C,$DE,$0A,$8D,$DE,$81,$2B,$26
 db $06,$8D,$52,$8D,$0E,$20,$F2,$81
 db $2D,$26,$15,$8D,$02,$20,$F4,$8D
 db $44,$20,$BE,$BD,$06,$A0,$08,$08
L0493 adda $01,x
 adcb $00,x
 staa $01,x
 stab $00,x
 rts
 db $BD,$05,$B8,$8D,$31,$8D,$A5,$DE
 db $0A,$39,$8D,$AE,$81,$3D,$26,$15
 db $31,$31,$5C,$20,$0D,$5F,$8D,$F2
 db $8D,$12,$26,$0A,$8D,$EC,$81,$3E
 db $26,$03,$5C,$08,$4F,$39,$8D,$F6
 db $26,$FB,$8D,$DE,$81,$3C,$26,$F5
 db $CB,$04,$20,$EF,$8D,$5E,$DF,$0A
 db $DE,$80,$39,$8D,$8A,$8D,$D6,$5D
 db $27,$E3,$37,$8D,$82,$BD,$06,$A0
 db $DE,$80,$A0,$01,$E2,$00,$33,$2D
 db $07,$2E,$03,$4D,$27,$01,$57,$57
 db $C4,$01,$E7,$01,$6F,$00,$DE,$04
 db $39
L04FD bsr L0525
 bcc L0524
 clrb
 stab $05
L0504 stab $04
 anda #$0F
 staa $15
 ldaa $05
 asla
 rolb
 asla
 rolb
 adda $05
 adcb $04
 asla
 rolb
 adda $15
 staa $05
 adcb #$00
 inx
 bsr L0525
 bcs L0504
 ldaa $05
 sec
L0524 rts
L0525 jsr L05AA
 cmpa #$30
 clc
 blt L052F
 cmpa #$3A
L052F rts
 db $8D,$33,$8D,$76,$81,$2A,$26,$0B
 db $8D,$14,$BD,$03,$E9,$DF,$80,$DE
 db $0A,$20,$EF,$81,$2F,$26,$E8,$8D
 db $05,$BD,$03,$9A,$20,$EF,$8D,$15
 db $7E,$04,$D2,$08,$BD,$02,$D2,$20
 db $32,$8D,$0A,$BD,$06,$A0,$8D,$63
 db $A6,$00,$5F,$20,$24,$08,$8D,$95
 db $25,$21,$81,$23,$27,$EB,$81,$24
 db $27,$E1,$DF,$0A,$CE,$08,$F1
L0577 jsr L0308
 ldaa $01,x
 psha
 ldaa $00,x
 psha
 ldx $0A
 rts
 db $8D,$3E,$A6,$01,$E6,$00,$DE,$0A
 db $DF,$04,$DE,$80,$09,$09,$9C,$10
 db $2F,$08,$BD,$04,$97,$DF,$80,$DE
 db $04,$39,$C6,$96,$7E,$08,$59,$C6
 db $A0,$20,$F9,$C6,$AA,$20,$F5
L05AA jmp L0456
 db $8D,$68,$24,$D2,$A6,$00,$81,$28
 db $26,$EB,$08,$BD,$04,$D7,$A6,$00
 db $81,$29,$26,$E1,$08,$39,$DF,$0A
 db $97,$05,$D7,$04,$DE,$04,$39,$BD
 db $04,$D7,$A6,$00,$81,$2C,$26,$D1
 db $08,$8D,$E0,$DF,$04,$DE,$80,$BD
 db $03,$9A,$20,$B4,$96,$07,$D6,$06
 db $DB,$07,$89,$95,$C9,$AB,$D7,$07
 db $97,$06,$8D,$9A,$20,$E3,$8D,$02
 db $20,$92,$BD,$18,$36,$37,$8D,$0D
 db $36,$37,$8D,$09,$36,$37,$07,$36
 db $8D,$B4,$DF,$0A,$3B,$A6,$00,$81
 db $2C,$26,$04,$08,$7E,$06,$9E,$4F
 db $5F,$39,$8D,$91,$81,$40,$27,$0C
 db $81,$41,$25,$26,$81,$5A,$22,$22
 db $48,$5F,$08,$39,$BD,$05,$4E,$BD
 db $06,$A0,$C5,$C0,$26,$11,$0D,$49
 db $59,$9B,$B9,$D9,$B8,$D1,$BA,$26
 db $02,$91,$BB,$24,$02,$0C,$39,$7E
 db $02,$26,$0D,$39,$BD,$04,$A6,$C6
 db $B4,$7E,$08,$59,$BD,$06,$17,$25
 db $F6,$97,$03,$D7,$02,$8D,$ED,$8D
 db $40,$DF,$0A,$DE,$02,$39,$C6,$BE
 db $20,$E7,$5F,$37,$BD,$04,$FD,$25
 db $4F,$7E,$02,$BA,$BD,$05,$65,$8D
 db $2A,$8D,$DE,$16,$20,$63,$9F,$0C
 db $35,$DE,$BC,$8C,$A0,$4A,$27,$DE
 db $09,$09,$AF,$00,$DF,$BC,$30,$9E
 db $0C,$39,$DE,$BC,$8C,$A0,$80,$27
 db $CD,$9F,$0C,$AE,$00,$08,$08,$20
 db $EB,$8D,$16,$DF,$04,$DE,$80,$8C
 db $00,$80,$27,$A3,$A6,$01,$E6,$00
 db $08,$08,$DF,$80,$DE,$04,$39,$DE
 db $0A,$7E,$04,$D7,$4F,$36,$8D,$E1
 db $BD,$01,$A6,$32,$4D,$27,$02,$8D
 db $B5,$BD,$02,$72,$24,$04,$C6,$C8
 db $20,$5A,$7E,$02,$AF,$BD,$04,$56
 db $81,$23,$27,$98,$BD,$06,$51,$A7
 db $01,$E7,$00,$DE,$0A,$39,$8D,$F4
 db $96,$03,$D6,$02,$BD,$05,$8B,$BD
 db $03,$03,$8C,$09,$10,$26,$33,$8D
 db $BE,$BD,$03,$03,$8C,$09,$16,$27
 db $08,$86,$01,$5F,$BD,$05,$89,$20
 db $04,$8D,$AC,$DF,$0A,$96,$0B,$D6
 db $0A,$BD,$05,$8B,$96,$03,$D6,$02
 db $DE,$BE,$8C,$01,$00,$27,$12,$8D
 db $14,$24,$0C,$DE,$BE,$8C,$00,$C0
 db $26,$07,$C6,$D2,$7E,$08,$59,$8D
 db $58,$8D,$10,$20,$4F,$BD,$02,$FC
 db $27,$08,$8D,$4D,$8C,$01,$00,$26
 db $F4,$0D,$39,$8D,$00,$8D,$00,$BD
 db $06,$A0,$09,$09,$7E,$04,$97,$C6
 db $DC,$20,$D9,$BD,$06,$17,$DF,$0A
 db $DE,$BE,$24,$04,$A6,$01,$E6,$00
 db $8D,$DA,$25,$EB,$DF,$BE,$A6,$05
 db $E6,$04,$EE,$00,$BD,$04,$93,$DE
 db $BE,$E1,$02,$0D,$2D,$07,$0C,$2E
 db $04,$A1,$03,$27,$13,$46,$A8,$04
 db $2B,$0E,$8D,$05,$DF,$BE,$DE,$0A
 db $39,$8D,$00,$08,$08,$08,$08,$39
 db $EE,$06,$39,$DF,$02,$96,$02,$27
 db $41,$DE,$10,$DF,$00,$DE,$02,$BD
 db $03,$72,$26,$02,$8D,$37,$BD,$06
 db $17,$25,$2F,$36,$37,$DF,$02,$DE
 db $00,$8D,$37,$26,$09,$86,$3F,$8D
 db $36,$8D,$32,$BD,$01,$2C,$BD,$06
 db $9E,$8D,$1A,$DF,$00,$30,$EE,$00
 db $31,$31,$BD,$04,$97,$DE,$02,$8D
 db $19,$27,$0F,$81,$2C,$26,$03,$08
 db $20,$CC,$7E,$01,$6B,$8D,$04,$26
 db $01,$08,$39,$36,$8D,$04,$81,$2C
 db $32,$39,$7E,$04,$56
L07EA ldaa #$20
L07EC jmp L043F
 db $5F,$86,$01,$BD,$01,$A6,$C6,$7F
 db $86,$FF,$36,$8D,$EB,$32,$27,$0E
 db $BD,$06,$9E,$BD,$01,$A6,$8D,$D9
 db $26,$04,$08,$BD,$06,$9E,$97,$0D
 db $D7,$0C,$DE,$0C,$2E,$05,$CE,$7F
 db $FF,$DF,$0C,$BD,$02,$7A,$20,$02
 db $8D,$10,$96,$0D,$D6,$0C,$BD,$02
 db $FC,$24,$F5,$86,$03,$8D,$BE
L082E jmp L01CB
L0831 ldaa #$02
 bsr L07EC
 bsr L0849
 inx
 ldaa #$20
 bsr L0850
L083C stx $04
 ldx #L0933
 bsr L0853
 clr MON_0014
L0846 ldx $04
 rts
L0849 stx $04
L084B jsr L0401
 bra L0846
L0850 bsr L07EC
 inx
L0853 ldaa $00,x
 bne L0850
 inx
 rts
L0859 lds #$A047
 bsr L083C
 ldx #ERROR_MSG
 bsr L0853
 tba
 clrb
 bsr L0874
 ldx $0E
 bmi L082E
 bsr L083C
 bsr L0831
 bra L082E
 db $BD,$06,$9E
L0874 psha
 pshb
 stx $04
 tsx
 bsr L084B
 pulb
L087C pula
 rts
KEYWORD_TABLE db $4C

 db $49,$53,$D4,$07,$EF,$4C,$4F,$41
 db $C4,$01,$96,$52,$55,$CE,$02,$AB
 db $45,$D8,$E0,$D0,$41,$55,$54,$CF
 db $01,$9C,$4E,$45,$D7
L089C db $01
 db $C9,$4C,$45,$D4,$06,$D2,$49,$C6
 db $02,$94,$47,$4F,$54,$CF,$06,$B9
 db $47,$4F,$53,$55,$C2,$06,$BA,$52
 db $45,$D4,$06,$8F,$4E,$45,$58,$D4
 db $07,$50,$46,$4F,$D2,$06,$E3,$54
 db $48,$45,$CE,$06,$67,$52,$45,$CD
 db $02,$6D,$50,$52,$49,$4E,$D4,$03
 db $2C,$49,$4E,$50,$55,$D4,$07,$90
 db $50,$D2,$03,$2C,$49,$CE,$07,$90
 db $53,$54,$4F,$D0,$01,$AB,$45,$4E
 db $C4,$01,$CB,$FF,$06,$D2,$52,$4E
 db $44,$A8,$05,$E1,$41,$42,$53,$A8
 db $04,$9C,$4D,$4F,$44,$A8,$05,$CC
 db $55,$53,$52,$A8,$05,$F3,$FF,$05
 db $AD,$54,$CF,$12,$34,$53,$54,$45
 db $D0,$AB,$CD,$43,$48,$52,$A8,$03
 db $60,$54,$41,$42,$A8,$03,$65,$FF
 db $08,$71
ERROR_MSG db $45
 db $52,$52,$4F,$52,$20,$00
READY_MSG db $52
 db $45,$41,$44,$59
L0933 db $0D
 db $0A,$FF,$FF,$FF,$FF,$FF,$00,$05
 db $CE,$3D,$17,$DF
L0940 jsr MON_E1AC
 cmpa #$60
 bcs L0949
 suba #$20
L0949 cmpa #$25
 bne L094F
 ldaa #$40
L094F rts
AUTO_HELPER db $BD
 db $06,$9E,$6D,$00,$26,$0B,$80,$0A
 db $C2,$00,$97,$09,$D7,$08,$7E,$01
 db $DC,$39
