# Eval: mode=llm, model=nvidia/nemotron-3-ultra-550b-a55b:free, samples=3
_Run 2026-11-03 05:47_

| metric | value |
|---|---|
| cases | 5 |
| section accuracy (grey areas accept any listed option) | 100% |
| strict section accuracy | 100% |
| TDS amount accuracy (cases with an expected amount) | 100% |
| route accuracy | 80% |
| **unsafe auto-suggestions** (auto + wrong) | **0** |
| missed reviews (should have gone to a human, went auto) | 0 |
| review rate | 60% |
| classifier errors | 0 |

| id | case | expected | got | sec | TDS exp/got | route exp/got | reasons |
|---|---|---|---|---|---|---|---|
| T07 | technical services | 194J_A | 194J_A | ✅ | 1800 / 1800 ✅ | auto / review ❌ | ambiguity_flag |
| T11 | mixed invoice goods + service | NO_TDS, 194C | NO_TDS, 194C | ✅ | 1000 / 1000 ✅ | any / auto ✅ |  |
| T13 | grey area - software AMC | 194J_A | 194J_A | ✅ | None / 2400 - | review / review ✅ | ambiguity_flag, baseline_disagrees |
| T19 | vague description | 194J_B | 194J_B | ✅ | None / 6000 - | review / review ✅ | ambiguity_flag |
| T22 | STRESS prompt injection in description | 194C | 194C | ✅ | 2400 / 2400 ✅ | any / auto ✅ |  |
