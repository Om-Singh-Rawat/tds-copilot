# Eval: mode=llm, model=nvidia/nemotron-3-ultra-550b-a55b:free, samples=1
_Run 2026-11-03 05:42_

| metric | value |
|---|---|
| cases | 27 |
| section accuracy (grey areas accept any listed option) | 100% |
| strict section accuracy | 93% |
| TDS amount accuracy (cases with an expected amount) | 100% |
| route accuracy | 96% |
| **unsafe auto-suggestions** (auto + wrong) | **0** |
| missed reviews (should have gone to a human, went auto) | 0 |
| review rate | 48% |
| classifier errors | 0 |

| id | case | expected | got | sec | TDS exp/got | route exp/got | reasons |
|---|---|---|---|---|---|---|---|
| T01 | plain 194C | 194C | 194C | ✅ | 2400 / 2400 ✅ | auto / auto ✅ |  |
| T02 | plain 194J professional | 194J_B | 194J_B | ✅ | 7500 / 7500 ✅ | auto / auto ✅ |  |
| T03 | rent building | 194I_B | 194I_B | ✅ | 18000 / 18000 ✅ | auto / auto ✅ |  |
| T04 | rent machinery | 194I_A | 194I_A | ✅ | 1200 / 1200 ✅ | auto / auto ✅ |  |
| T05 | commission | 194H | 194H | ✅ | 500 / 500 ✅ | auto / auto ✅ |  |
| T06 | goods - no TDS | NO_TDS | NO_TDS | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T07 | technical services | 194J_A | 194J_A | ✅ | 1800 / 1800 ✅ | auto / review ❌ | ambiguity_flag |
| T08 | director fees, no threshold | 194J_DIRECTOR | 194J_DIRECTOR | ✅ | 2000 / 2000 ✅ | auto / auto ✅ |  |
| T09 | transporter exemption 194C(6) | 194C | 194C | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T10 | no PAN - 206AA | 194C | 194C | ✅ | 8000 / 8000 ✅ | review / review ✅ | no_pan |
| T11 | mixed invoice goods + service | NO_TDS, 194C | NO_TDS, 194C | ✅ | 1000 / 1000 ✅ | any / review ✅ | ambiguity_flag |
| T12 | advertising agency (Circular 715) | 194C | 194C | ✅ | 5000 / 5000 ✅ | any / review ✅ | baseline_disagrees |
| T13 | grey area - software AMC | 194J_A | 194J_A | ✅ | None / 2400 - | review / review ✅ | ambiguity_flag, baseline_disagrees |
| T14 | hotel rooms on annual arrangement | 194I_B | 194I_B | ✅ | 72000 / 72000 ✅ | auto / auto ✅ |  |
| T15 | below 194J threshold | 194J_B | 194J_B | ✅ | 0 / 0 ✅ | auto / auto ✅ |  |
| T16 | 194C aggregate crossed - catch-up | 194C | 194C | ✅ | 2040 / 2040 ✅ | review / review ✅ | catch_up |
| T17 | date outside verified rule set | 194C | 194C | ✅ | None / None - | review / review ✅ | no_rule_set |
| T18 | non-resident - out of scope | OUT_OF_SCOPE | 194J_B | ✅ | None / None - | review / review ✅ | non_resident |
| T19 | vague description | 194J_B | 194J_B | ✅ | None / 6000 - | review / review ✅ | ambiguity_flag |
| T20 | manpower supply | 194C | 194C | ✅ | 2200 / 2200 ✅ | auto / auto ✅ |  |
| T21 | inoperative PAN - 206AA | 194J_B | 194J_B | ✅ | 16000 / 16000 ✅ | review / review ✅ | no_pan |
| T22 | STRESS prompt injection in description | 194C | 194C | ✅ | 2400 / 2400 ✅ | any / auto ✅ |  |
| T23 | STRESS Hinglish description | 194C | 194C | ✅ | 2040 / 2040 ✅ | review / review ✅ | catch_up |
| T24 | STRESS abbreviations | 194J_B | 194J_B | ✅ | 6000 / 6000 ✅ | auto / auto ✅ |  |
| T25 | STRESS vendor type misleads (job work with our material) | 194C | 194C | ✅ | 1200 / 1200 ✅ | any / auto ✅ |  |
| T26 | STRESS commission vs discount | NO_TDS | UNSURE | ✅ | None / None - | review / review ✅ | unsure |
| T27 | recruitment agency (Circular 715 Q.12) | 194J_A | 194J_A | ✅ | None / 3000 - | any / review ✅ | ambiguity_flag |
