# Intrabar Stress DD Distributions

Each event is one peak-to-trough intrabar stress cycle. The peak is based on close-equity highs; the trough uses the intrabar stress equity from the replay. Per-strategy event files live next to each `equity_curve.csv` as `intrabar_stress_dd_events.csv`.

| Candidate | Instrument | Events | Max Stress DD | P50 | P75 | P90 | P95 | >=75% Max | >=90% Max | Tail Signal |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| NQ ATR weekly 2-initial / 3-add / 6-max | NQ | 335 | $-428,375.00 | $5,640.00 | $19,050.00 | $39,468.00 | $61,521.00 | 1 | 1 | max stress is an outlier |
| NQ ATR daily 3-initial 10-max | NQ | 212 | $-308,655.00 | $15,375.00 | $35,707.50 | $73,562.00 | $111,026.25 | 4 | 1 | large stress recurs |
| ES ATR daily 3-initial 10-max | ES | 120 | $-275,712.50 | $10,875.00 | $21,131.25 | $39,071.25 | $72,676.87 | 1 | 1 | max stress is an outlier |
| NQ ATR daily ladder 1/1/2/2/2 10-max | NQ | 170 | $-255,950.00 | $18,002.50 | $39,862.50 | $75,798.00 | $132,796.00 | 5 | 3 | large stress recurs |
| YM ATR weekly 2-initial / 3-add / 6-max | YM | 293 | $-245,550.00 | $3,120.00 | $7,050.00 | $15,972.00 | $39,262.00 | 2 | 1 | largest stress is elevated but recurring |
| ES ATR daily ladder 1/1/2/2/2 10-max | ES | 93 | $-245,025.00 | $10,500.00 | $23,500.00 | $43,017.50 | $104,870.00 | 1 | 1 | max stress is an outlier |
| YM ATR daily ladder 1/1/2/2/2 10-max | YM | 72 | $-224,330.00 | $4,645.00 | $11,760.00 | $17,950.00 | $38,095.75 | 1 | 1 | max stress is an outlier |
| NQ Monthly ORB restricted scaleout3 | NQ | 116 | $-218,668.75 | $2,148.75 | $6,361.25 | $23,421.25 | $34,105.94 | 1 | 1 | max stress is an outlier |
| ES ATR weekly 2-initial / 3-add / 6-max | ES | 306 | $-199,637.50 | $6,300.00 | $13,106.25 | $34,762.50 | $59,962.50 | 5 | 2 | large stress recurs |
| NQ Monthly ORB restricted scaleout3 boundary-stop entry | NQ | 285 | $-168,163.75 | $2,890.00 | $7,905.00 | $22,735.00 | $35,829.00 | 1 | 1 | max stress is an outlier |
| YM ATR daily 3-initial 10-max | YM | 108 | $-165,935.00 | $4,625.00 | $11,750.00 | $29,298.50 | $65,079.75 | 2 | 1 | largest stress is elevated but recurring |
| NQ Yearly ORB scaleout3 | NQ | 122 | $-133,860.00 | $5,845.00 | $13,190.00 | $32,844.00 | $56,495.81 | 3 | 2 | large stress recurs |
| ES Monthly ORB restricted scaleout3 | ES | 34 | $-127,996.88 | $831.25 | $1,885.94 | $3,755.00 | $4,746.40 | 1 | 1 | max stress is an outlier |
| ES Monthly ORB restricted scaleout3 boundary-stop entry | ES | 217 | $-95,793.75 | $2,925.00 | $6,325.00 | $16,647.50 | $26,410.62 | 1 | 1 | max stress is an outlier |
| YM Yearly ORB scaleout3 | YM | 87 | $-75,305.00 | $845.00 | $1,765.00 | $6,202.00 | $12,702.00 | 2 | 1 | largest stress is elevated but recurring |
| ES Yearly ORB scaleout3 | ES | 40 | $-70,612.50 | $3,056.25 | $6,478.12 | $35,554.69 | $38,830.16 | 1 | 1 | max stress is an outlier |
| YM Monthly ORB restricted scaleout3 | YM | 29 | $-70,177.50 | $6,060.00 | $12,680.00 | $36,443.50 | $46,923.50 | 1 | 1 | max stress is an outlier |
| YM Monthly ORB restricted scaleout3 boundary-stop entry | YM | 236 | $-47,753.75 | $2,322.50 | $5,180.62 | $14,980.00 | $22,242.19 | 4 | 3 | large stress recurs |
| MNQ ATR weekly 2-initial / 3-add / 6-max | MNQ | 171 | $-42,806.50 | $1,746.00 | $3,027.00 | $6,003.00 | $11,676.00 | 1 | 1 | max stress is an outlier |
| MNQ ATR daily 3-initial 10-max | MNQ | 156 | $-29,264.00 | $2,220.00 | $4,496.88 | $7,960.75 | $13,867.75 | 4 | 1 | large stress recurs |
| MES ATR daily 3-initial 10-max | MES | 56 | $-27,550.00 | $800.00 | $1,526.25 | $3,062.50 | $5,706.56 | 1 | 1 | max stress is an outlier |
| MNQ ATR daily ladder 1/1/2/2/2 10-max | MNQ | 134 | $-25,610.00 | $2,292.00 | $4,742.25 | $8,140.95 | $14,553.02 | 5 | 2 | large stress recurs |
| MES ATR daily ladder 1/1/2/2/2 10-max | MES | 41 | $-24,488.75 | $640.00 | $1,437.50 | $3,633.75 | $6,996.25 | 1 | 1 | max stress is an outlier |
| MNQ Monthly ORB restricted scaleout3 | MNQ | 66 | $-20,808.75 | $423.00 | $1,243.50 | $2,696.12 | $3,498.75 | 1 | 1 | max stress is an outlier |
| MYM ATR daily ladder 1/1/2/2/2 10-max | MYM | 32 | $-19,514.50 | $429.50 | $1,891.00 | $6,189.30 | $12,101.12 | 1 | 1 | max stress is an outlier |
| MYM ATR weekly 2-initial / 3-add / 6-max | MYM | 107 | $-18,929.50 | $846.00 | $1,743.00 | $4,606.20 | $8,608.20 | 1 | 1 | max stress is an outlier |
| MES ATR weekly 2-initial / 3-add / 6-max | MES | 147 | $-17,212.50 | $765.00 | $1,338.75 | $3,150.00 | $5,756.25 | 2 | 1 | largest stress is elevated but recurring |
| MNQ Monthly ORB restricted scaleout3 boundary-stop entry | MNQ | 160 | $-16,881.38 | $574.50 | $1,288.12 | $2,915.97 | $5,380.52 | 1 | 1 | max stress is an outlier |
| MNQ Yearly ORB scaleout3 | MNQ | 97 | $-13,378.50 | $759.00 | $1,506.00 | $3,434.40 | $6,593.60 | 3 | 2 | large stress recurs |
| MYM ATR daily 3-initial 10-max | MYM | 52 | $-13,205.50 | $1,009.50 | $1,988.25 | $3,979.95 | $8,243.57 | 3 | 3 | large stress recurs |
| MYM Monthly ORB restricted scaleout3 | MYM | 19 | $-8,606.25 | $664.50 | $1,284.00 | $3,282.12 | $3,928.38 | 1 | 1 | max stress is an outlier |
| MES Monthly ORB restricted scaleout3 | MES | 29 | $-7,443.75 | $240.00 | $515.00 | $1,111.94 | $3,210.13 | 1 | 1 | max stress is an outlier |
| MES Yearly ORB scaleout3 | MES | 3 | $-7,143.75 | $997.50 | $4,070.62 | $5,914.50 | $6,529.12 | 1 | 1 | max stress is the dominant tail event |
| MES Monthly ORB restricted scaleout3 boundary-stop entry | MES | 107 | $-6,512.81 | $393.75 | $740.15 | $2,256.75 | $3,138.75 | 3 | 1 | large stress recurs |
| MYM Monthly ORB restricted scaleout3 boundary-stop entry | MYM | 110 | $-5,504.12 | $333.88 | $961.88 | $2,127.90 | $3,204.30 | 2 | 1 | largest stress is elevated but recurring |
| MYM Yearly ORB scaleout3 | MYM | 20 | $-5,407.50 | $527.25 | $1,065.75 | $3,577.30 | $5,180.45 | 2 | 2 | large stress recurs |
