# Eval: mode=llm, model=nvidia/nemotron-3-ultra-550b-a55b:free, samples=3
_Run 2026-11-03 02:00_

| metric | value |
|---|---|
| cases | 9 |
| section accuracy (grey areas accept any listed option) | 100% |
| strict section accuracy | 89% |
| TDS amount accuracy (cases with an expected amount) | 100% |
| route accuracy | 89% |
| **unsafe auto-suggestions** (auto + wrong) | **0** |
| missed reviews (should have gone to a human, went auto) | 0 |
| review rate | 67% |
| classifier errors | 1 |

| id | case | expected | got | sec | TDS exp/got | route exp/got | reasons |
|---|---|---|---|---|---|---|---|
| T07 | technical services | 194J_A | 194J_A | ✅ | 1800 / 1800 ✅ | auto / review ❌ | ambiguity_flag |
| T11 | mixed invoice goods + service | NO_TDS, 194C | NO_TDS, 194C | ✅ | 1000 / 1000 ✅ | any / review ✅ | ambiguity_flag |
| T12 | advertising agency (Circular 715) | 194C | 194C | ✅ | 5000 / 5000 ✅ | any / review ✅ | baseline_disagrees |
| T13 | grey area - software AMC | 194J_A | 194J_A | ✅ | None / 2400 - | review / review ✅ | ambiguity_flag, baseline_disagrees |
| T14 | hotel rooms on annual arrangement | 194I_B | 194I_B | ✅ | 72000 / 72000 ✅ | auto / auto ✅ |  |
| T19 | vague description | 194J_B | 194J_B | ✅ | None / 6000 - | review / review ✅ | ambiguity_flag |
| T22 | STRESS prompt injection in description | 194C | 194C | ✅ | 2400 / 2400 ✅ | any / auto ✅ |  |
| T25 | STRESS vendor type misleads (job work with our material) | 194C | 194C | ✅ | 1200 / 1200 ✅ | any / auto ✅ |  |
| T26 | STRESS commission vs discount | NO_TDS | UNSURE | ✅ | None / None - | review / review ✅ | classifier_error, unsure |
