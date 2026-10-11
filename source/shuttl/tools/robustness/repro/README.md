# Reproducers are three executable shell commands; clips are tracked corpus inputs.

## 192x144 weak-only linker regression

```sh
cd '/Users/yangcong/Downloads/华北五省/backend'
.venv/bin/python -m pytest -q tests/test_linker.py::test_weak_only_candidates
.venv/bin/python ../tools/robustness/python_one.py ../tools/robustness/corpus/192x144.mp4
```

Current source at `backend/app/services/tracking/linker.py:504` already guards empty strong detections (`if len(sk):`); focused regression passes 3/3. This lead is fixed in the inspected revision; no patch suggested.
