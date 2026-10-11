# V Workstream Bug Fixes (Re-review)

## BUG1: KILLED timing used match done time instead of script's kill time

**Root cause**: `timeline()` inferred kill time from the next run_start timestamp, but T4's next run started 5 minutes later (02:01:09Z) due to thermal throttling, so it showed 299s instead of 130s.

**Fix**: Added `parse_kill_time()` to read kills.txt (format: "t4 2026-10-01T01:58:20Z"), separate from tests.txt. The v5 script writes this marker when it sends SIGKILL.

**Verification**: Real T4 data now shows 130.0s (01:56:10Z → 01:58:20Z), not 299s.

## BUG2: Lost-before-first-checkpoint classified as F-P3 FAIL

**Root cause**: Code checked `start.frames < 7200` to determine if progress was lost before first checkpoint, but `start.frames` is the clip length (35999 for 10-min clips), not the progress made.

**Fix**: Changed logic to check `not had_checkpoint_activity` (no detect_partial_save with verdict=ok and no detect_partial_load with verdict=ok and next_frame > 0). Progress lost before any checkpoint activity is now INFO, not FAIL.

**Verification**: T4 KILLED run (130s detect, no saves, retry from 0) now shows:
- `lost_before_first=True` (INFO)
- `lost=False` (not F-P3 FAIL)
- Report: "PASS no detect retry threw away progress (F-P3): 0 lost"

## BUG3: MAC SLEPT test case

**Already covered**: test-v5-offline.sh test F has a 1900s sleep gap case.

## Test Coverage

### New pytest cases (3):
1. `test_bug1_kills_file_separate_from_tests` - Verifies parse_kill_time() reads kills.txt
2. `test_bug2_real_t4_lost_before_first_checkpoint` - Real T4 scenario: 130s killed run with no saves
3. `test_bug2_positive_f_p3_saved_then_retry_from_zero` - Positive case: saved checkpoint but retry from 0 → FAIL

### Results:
- pytest: **27 passed** (was 23)
- test-v5-offline.sh: **ALL CHECKS PASSED**

## Files Changed
- `judge.py`: Added parse_kill_time(), fixed lost_before_first logic
- `run-device-tests-v5.sh`: Writes kills.txt on SIGKILL
- `test_judge.py`: Added 3 new test cases (4 total with BUG3)
