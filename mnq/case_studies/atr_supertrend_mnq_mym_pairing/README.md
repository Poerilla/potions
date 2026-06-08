# ATR Supertrend MNQ + MYM Pairing

This combines the dynamic-sizing daily equity paths from the MNQ and MYM ATR Supertrend studies. Each market sizes itself independently by the same 3x historical MTM-DD rule, then the daily dollar PnL streams are summed.

| Variant | Start Capital | End Capital | Net | Combined DD | MNQ Alone Net/DD | MYM Alone Net/DD | Daily PnL Corr | DD Improvement vs MNQ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily primary, 3-initial | $74,486 | $826,662 | $752,177 | $-155,698 | $653,171 / $-140,925 | $99,006 / $-27,305 | 0.35 | $-14,772 |
| Daily primary, ladder 1/1/2/2/2 | $70,222 | $788,436 | $718,213 | $-143,462 | $640,430 / $-131,215 | $77,782 / $-25,340 | 0.34 | $-12,248 |
| Weekly primary, 3-initial | $71,446 | $1,721,234 | $1,649,788 | $-233,318 | $1,089,527 / $-234,080 | $560,260 / $-50,546 | 0.55 | $762 |
| Weekly primary, ladder 1/1/2/2/2 | $63,114 | $1,540,482 | $1,477,368 | $-219,157 | $1,043,250 / $-220,301 | $434,118 / $-48,196 | 0.55 | $1,144 |

Interpretation: negative or low daily PnL correlation is useful, but the combined DD still grows if MYM adds more absolute heat than it offsets. Compare `Combined DD` against MNQ-alone DD before deciding it diversifies the live account.
