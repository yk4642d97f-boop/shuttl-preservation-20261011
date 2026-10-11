#!/usr/bin/env python3
"""Run a built Swift app-pipeline driver one clip at a time."""
import cv2, json, os, pathlib, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]; ROB=ROOT/'tools/robustness'
BIN=pathlib.Path('/tmp/luna10/driver/release/RobustnessDriver'); OUT=ROB/'swift_results.jsonl'

def timeout_for(path):
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30; n=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; cap.release()
    return max(120,int(120+4*n/fps))

def main():
    OUT.write_text('')
    with OUT.open('a') as log:
        for clip in sorted(p for p in (ROB/'corpus').iterdir() if p.suffix.lower() in ('.mp4','.mov','.wav')):
            metric=pathlib.Path(tempfile.gettempdir())/f'shuttl-metrics-{clip.stem}.jsonl'
            metric.unlink(missing_ok=True); env=os.environ.copy(); env['SHUTTL_STAGE_METRICS']=str(metric)
            try:
                r=subprocess.run([str(BIN),'analyze',str(clip)],env=env,text=True,capture_output=True,timeout=timeout_for(clip))
                try: result=json.loads(r.stdout.strip().splitlines()[-1])
                except Exception: result={'clip':clip.name,'status':'exception','stdout':r.stdout[-2000:]}
                result.update(status=result.get('status','returned') if r.returncode==0 else 'crash',exit=r.returncode,stderr=r.stderr[-3000:])
            except subprocess.TimeoutExpired as e: result={'clip':clip.name,'status':'timeout','stdout':str(e.stdout)[-1000:]}
            result['metrics']=[json.loads(x) for x in metric.read_text().splitlines() if x.strip()] if metric.exists() else []
            peaks=[m.get(k) for m in result['metrics'] for k in ('footprint_peak_mb','peak_phys_footprint_mb','phys_footprint_peak_mb') if isinstance(m.get(k),(int,float))]
            result['max_memory_mb']=max(peaks,default='')
            log.write(json.dumps(result,ensure_ascii=False,default=str)+'\n'); log.flush()
            print(clip.name,result['status'],flush=True)
if __name__=='__main__': main()
