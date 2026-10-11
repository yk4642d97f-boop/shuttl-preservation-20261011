#!/usr/bin/env python3
"""Run Python reference serially; each clip is isolated behind a duration-scaled timeout."""
import cv2, json, os, pathlib, subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]; ROB=ROOT/'tools/robustness'; CORP=ROB/'corpus'
WORKER=ROB/'python_one.py'; OUT=ROB/'python_results.jsonl'

def timeout_for(path):
    cap=cv2.VideoCapture(str(path))
    fps=cap.get(cv2.CAP_PROP_FPS) or 30; n=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; cap.release()
    seconds=n/fps if fps>0 else 0
    return max(60,int(60+4*seconds))

def main():
    clips=sorted(p for p in CORP.iterdir() if p.suffix.lower() in ('.mp4','.mov','.m4v','.wav'))
    OUT.write_text('')
    with OUT.open('a') as log:
        for p in clips:
            env=os.environ.copy(); env.update(SHUTTL_DETECTOR='auto',PYTHONPATH=str(ROOT/'backend'),
                PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                NUMBA_CACHE_DIR='/tmp/luna10/numba',YOLO_CONFIG_DIR='/tmp/luna10/yolo')
            try:
                r=subprocess.run([str(ROOT/'backend/.venv/bin/python'),str(WORKER),str(p)],cwd=ROOT/'backend',
                    env=env,text=True,capture_output=True,timeout=timeout_for(p))
                try: row=json.loads(r.stdout.strip().splitlines()[-1])
                except Exception: row={'clip':p.name,'status':'exception','stdout':r.stdout[-8000:]}
                row.update(exit=r.returncode,stderr=r.stderr[-8000:])
                if r.returncode and row.get('status')=='returned': row['status']='crash'
            except subprocess.TimeoutExpired as e:
                row={'clip':p.name,'status':'timeout','stdout':str(e.stdout)[-2000:],'stderr':str(e.stderr)[-2000:]}
            log.write(json.dumps(row,ensure_ascii=False,default=str)+'\n'); log.flush()
            print(p.name,row['status'],flush=True)
if __name__=='__main__': main()
