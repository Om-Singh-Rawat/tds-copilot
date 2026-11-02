# Eval: mode=baseline
_Run 2026-11-03 02:35_

| metric | value |
|---|---|
| cases | 27 |
| section accuracy (grey areas accept any listed option) | 70% |
| strict section accuracy | 56% |
| TDS amount accuracy (cases with an expected amount) | 62% |
| route accuracy | 81% |
| **unsafe auto-suggestions** (auto + wrong) | **1** |
| missed reviews (should have gone to a human, went auto) | 2 |
| review rate | 52% |
| classifier errors | 0 |

| id | case | expected | got | sec | TDS exp/got | route exp/got | reasons |
|---|---|---|---|---|---|---|---|
| T01 | plain 194C | 194C | 194C | ✅ | 2400 / 2400 ✅ | auto / auto ✅ |  |
| T02 | plain 194J professional | 194J_B | 194J_B | ✅ | 7500 / 7500 ✅ | auto / auto ✅ |  |
| T03 | rent building | 194I_B | 194I_B | ✅ | 18000 / 18000 ✅ | auto / auto ✅ |  |
| T04 | rent machinery | 194I_A | 194I_A | ✅ | 1200 / 1200 ✅ | auto / auto ✅ |  |
| T05 | commission | 194H | 194H | ✅ | 500 / 500 ✅ | auto / auto ✅ |  |
| T06 | goods - no TDS | NO_TDS | NO_TDS | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T07 | technical services | 194J_A | 194J_A | ✅ | 1800 / 1800 ✅ | auto / auto ✅ |  |
| T08 | director fees, no threshold | 194J_DIRECTOR | 194J_DIRECTOR | ✅ | 2000 / 2000 ✅ | auto / auto ✅ |  |
| T09 | transporter exemption 194C(6) | 194C | 194C | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T10 | no PAN - 206AA | 194C | 194C | ✅ | 8000 / 8000 ✅ | review / review ✅ | no_pan |
| T11 | mixed invoice goods + service | NO_TDS, 194C | NO_TDS, UNSURE | ❌ | 1000 / None ❌ | any / review ✅ | unsure |
| T12 | advertising agency (Circular 715) | 194C | 194J_B | ❌ | 5000 / 25000 ❌ | any / auto ✅ ⚠️UNSAFE |  |
| T13 | grey area - software AMC | 194J_A | 194C | ✅ | None / 2400 - | review / auto ❌ |  |
| T14 | hotel rooms on annual arrangement | 194I_B | UNSURE | ❌ | 72000 / None ❌ | auto / review ❌ | unsure |
| T15 | below 194J threshold | 194J_B | 194J_B | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T16 | 194C aggregate crossed - catch-up | 194C | 194C | ✅ | 2040 / 2040 ✅ | review / review ✅ | catch_up |
| T17 | date outside verified rule set | 194C | 194C | ✅ | None / None - | review / review ✅ | no_rule_set |
| T18 | non-resident - out of scope | OUT_OF_SCOPE | 194J_B | ✅ | None / None - | review / review ✅ | non_resident |
| T19 | vague description | 194J_B | 194J_B | ✅ | None / 6000 - | review / auto ❌ |  |
| T20 | manpower supply | 194C | UNSURE | ❌ | 2200 / None ❌ | auto / review ❌ | unsure |
| T21 | inoperative PAN - 206AA | 194J_B | 194J_B | ✅ | 16000 / 16000 ✅ | review / review ✅ | no_pan |
| T22 | STRESS prompt injection in description | 194C | UNSURE | ❌ | 2400 / None ❌ | any / review ✅ | unsure |
| T23 | STRESS Hinglish description | 194C | UNSURE | ❌ | 2040 / None ❌ | review / review ✅ | unsure |
| T24 | STRESS abbreviations | 194J_B | UNSURE | ❌ | 6000 / None ❌ | auto / review ❌ | unsure |
| T25 | STRESS vendor type misleads (job work with our material) | 194C | UNSURE | ❌ | 1200 / None ❌ | any / review ✅ | unsure |
| T26 | STRESS commission vs discount | NO_TDS | UNSURE | ✅ | None / None - | review / review ✅ | unsure |
| T27 | recruitment agency (Circular 715 Q.12) | 194J_A | UNSURE | ✅ | None / None - | any / review ✅ | unsure |
