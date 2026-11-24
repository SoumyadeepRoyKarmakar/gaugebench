# Validation evidence

Everything on this page can be reproduced from the repository: the suites are regenerated from their seeds, and the numbers come from `runs/*/generation_log.json`, `runs/*/results/*.jsonl` and the per-task validation records in `runs/*/tasks/*/task.json`. Design rationale is in [TECHNICAL.md](TECHNICAL.md).

## 1. Automated tests (23, all passing)

Full log: [validation/pytest.log](validation/pytest.log). Reproduce with `python -m pytest -v` (or inside Docker, see the README).

| Test | What it proves |
|---|---|
| `test_scale_roundtrip` (×4) | value ↔ angle is exact for linear, offset (negative range), square-root and log scales |
| `test_ticks_sorted_and_ends_labeled` | tick generation is ordered and both ends of every scale are labelled |
| `test_independent_reader_accuracy` | the pixel reader recovers the drawn value within tolerance across random dials |
| `test_validator_rejects_corrupted_key` | **mutation test:** shift the answer key by 3 tolerances and the validator rejects the task, every time |
| `test_generation_is_deterministic` | the same seed produces byte-identical tasks |
| `test_every_published_task_passed_all_checks` | no task is published with a failing check |
| `test_parsers` | `ANSWER:` parsing for numbers (signs, commas, units) and choices |
| `test_scoring_separates_right_from_near_miss` | the key scores correct; 2.5 tolerances off scores wrong |
| `test_dual_scale_and_level_readers` | independent readers for two-ring dials and sight-glasses |
| `test_gemini_adapter_offline` | the Gemini adapter's request, retry and error handling, with no network |
| `test_label_overlap_detected` | cramped dials whose printed numbers collide are rejected |
| `test_new_instrument_readers` | clock-meter, vernier and digital readers recover the drawn value; the vernier reader notices a wrong key |
| `test_new_families_publish_valid_tasks` | the three new instruments publish valid, correctly scored tasks |
| `test_inspection_round_publishes_valid_tasks_and_scores_partial_credit` | inspection rounds: every camera passes validation; a reading 3 tolerances off, a missed alarm and a false alarm are each detected |
| `test_studio_api_hides_key_until_answered` | the Studio never sends the answer key or true needle value before the reader answers |
| `test_challenge_api_hides_key_until_answered` | Challenge rounds carry no key, tolerance or model answer; path traversal is refused |
| `test_hints_never_contain_the_answer` | no hint, for any family, leaks the value |
| `test_public_mode_protects_key_and_quota` | hosted mode: the API key never reaches the browser, unlisted models are refused, per-visitor and daily caps hold, answers are cached, error details stay server-side, answer files are not served |
| `test_fetch_suite_unpacks_and_refuses_unsafe_zips` | hosted suite downloads refuse zip entries that escape the target folder or aren't suite files |
| `test_evaluate_limit_keeps_earlier_answers` | a partial evaluation run never deletes answers cached by an earlier run |

## 2. Generation metrics

Every candidate is validated; failures are discarded and regenerated with a new seed. One candidate can fail several checks.

| Suite | Published | Candidates | Rejected | Time | Top rejection reasons |
|---|---|---|---|---|---|
| `v2` (main) | 384 | 636 | 252 (40%) | 247 s | glare over the needle 185, printed numbers overlapping 146, needle on a zone boundary 51, needle near a danger boundary 29, set-point needle too faint 21 |
| `instruments` | 24 | 42 | 18 (43%) | 9 s | meter pointer on a printed number 7, glare over the needle 7, meter dials not re-readable 4, vernier alignment not resolvable 4 |
| `rounds` | 20 | 43 | 23 camera re-shoots | 26 s | needle near a danger boundary 10, glare over the needle 8, numbers overlapping 5 |
| `sample` | 70 | 110 | 40 (36%) | 34 s | glare over the needle 19, numbers overlapping 11 |

**Independent re-read agreement** (from each published task's `pixel_reread` check):

| Suite | Needles re-read | Within tolerance | Mean error | Worst error |
|---|---|---|---|---|
| `v2` | 623 | 623 (100%) | 0.04 × tolerance | 0.50 × tolerance |
| `rounds` | 106 | 106 (100%) | 0.05 × tolerance | 0.40 × tolerance |
| `sample` | 114 | 114 (100%) | 0.04 × tolerance | 0.45 × tolerance |

## 3. Scoring sanity (validation matrix)

| Answerer | `v2` (384) | `instruments` (24) | `rounds` (20) | Expected |
|---|---|---|---|---|
| `oracle` (returns the key) | 100% | 100% | 100% | 100% |
| `near_miss` (just outside tolerance / wrong option) | 0% | 0% | 0% | 0% |
| `random` | 7.0% | 0% | 0% | chance |
| `shortcut` (cheap heuristics) | 12.0% | 16.7% | 0% | low |
| **Gemini 3.5 Flash-Lite** | **51.8%** | **25.0%** | **0%** perfect rounds | measured |

Gemini produced a parsable `ANSWER:` line for all 428 of its answers (0 parse failures).

## 4. Failure cases

From the reports (`runs/*/report.html` has the full failure galleries with images):

- **Snapping to a tick.** A needle at 4.6 bar reported as "approximately 4". 77 of 175 wrong numbers in `v2` were within 2× the tolerance; only 1 was off by more than 20×.
- **Vernier caliper, 0 of 8.** Typical misses: key 57.5 mm answered 5.9 (read the centimetre numbers as millimetres); key 128.5 mm answered 13.7; key 45.5 mm answered 42.6 (picked the wrong aligned line).
- **Digital display, 5 of 8.** All three misses ignored the lit ×10/×100 indicator: key 984 answered 9.84; key 589100 answered 5891; key −160 answered −1.6. The digits themselves were read correctly.
- **Inspection rounds, 0 of 20 perfect.** 34 of 106 readings correct, 16 of 31 red gauges flagged, 4 false alarms; the alarm list was exactly right in 9 rounds.
- **Range trap and wrong ring avoided.** Panel max: 0 of 1 wrong answers picked the furthest-turned needle. Dual scale: 0 of 7 wrong answers were the other ring's reading; the model found the right ring and then misread it.

## 5. Problems found and fixed

No generated task was ever corrected by hand: every fix below was made in code, and affected suites were regenerated from their seeds.

| Problem | How it was found | Fix |
|---|---|---|
| Printed numbers on cramped dials could run together | Reviewing generated dials with many labels | New `labels_do_not_overlap` check (146 rejections in `v2`); test `test_label_overlap_detected` |
| Studio could reveal the true needle value early | Review of the API payload: pixel re-read details contained the value | Re-read details are redacted until the reader answers; test `test_studio_api_hides_key_until_answered` |
| Hardest-level tasks sometimes failed to generate in the Studio | All 25 attempts rejected under fixed harsh conditions | Conditions are re-sampled per attempt when a level is chosen, as in suite generation |
| Free-tier daily quota stopped evaluation runs | 429 errors mid-run | Daily-cap errors fail fast; failed calls are never cached as answers and are retried on the next run |
| A partial `evaluate --limit` run deleted earlier answers | Found during the final evaluation | The results file now keeps every cached answer; test `test_evaluate_limit_keeps_earlier_answers` |
| A whole inspection round was discarded when one camera failed | Low acceptance at the hardest level | Only the failing camera is re-shot; re-shoots are counted in the rejection log |
| A hint matched a reading by coincidence ("×10" vs a reading of 10) | `test_hints_never_contain_the_answer` | Hints contain no numbers |
