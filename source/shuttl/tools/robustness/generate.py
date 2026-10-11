#!/usr/bin/env python3
"""Deterministic synthetic robustness corpus. Run from repo root or anywhere."""
from pathlib import Path
import cv2, json, numpy as np, shutil, struct, wave
OUT = Path(__file__).resolve().parent / "corpus"
SEED = 81010

def frame(w,h,kind,i=0,n=1):
    rng=np.random.default_rng(SEED+i); im=np.zeros((h,w,3),np.uint8)
    if kind=='white': im[:]=255
    elif kind=='random': im[:]=rng.integers(0,256,(h,w,3),dtype=np.uint8)
    elif kind not in ('black','audio'):
        im[:]=(35,85,35)
        y0,y1=(.15,.52) if kind=='far_half' else (.15,.9)
        if kind not in ('far_half',):
            for x in np.linspace(.12,.88,6): cv2.line(im,(int(w*x),int(h*y0)),(int(w*x),int(h*y1)),(230,230,230),max(1,w//600))
        cv2.rectangle(im,(int(w*.12),int(h*y0)),(int(w*.88),int(h*y1)),(240,240,240),max(1,w//500))
        if kind in ('shake','zoom','flicker','person','two_courts','upside'):
            if kind=='flicker' and i%2: im=(im*.35).astype(np.uint8)
            if kind=='shake': im=np.roll(im,(i%7-3,i%5-2),(1,0))
            if kind=='zoom': im=cv2.resize(im,(int(w*(1+.12*i/max(n,1))),int(h*(1+.12*i/max(n,1)))))[:h,:w]
            if kind=='two_courts':
                cv2.rectangle(im,(w//2,0),(w-1,h-1),(35,85,35),-1)
                cv2.rectangle(im,(int(w*.56),int(h*.2)),(int(w*.96),int(h*.85)),(245,245,245),max(1,w//500))
                for x in np.linspace(.58,.94,4): cv2.line(im,(int(w*x),int(h*.2)),(int(w*x),int(h*.85)),(230,230,230),max(1,w//600))
            if kind=='person':
                x=int(w*(.15+.7*i/max(n-1,1))); cv2.ellipse(im,(x,int(h*.55)),(w//18,h//7),0,0,360,(30,30,150),-1)
                cv2.line(im,(x,int(h*.62)),(x,int(h*.9)),(20,20,130),max(2,w//80))
            if kind=='upside': im=cv2.rotate(im,cv2.ROTATE_180)
    return im

def audio_only():
    p=OUT/'audio_only.wav'; rate=16000; n=rate//2
    with wave.open(str(p),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        t=np.arange(n,dtype=np.float32)/rate
        pcm=(8000*np.sin(2*np.pi*440*t)).astype('<i2'); f.writeframes(pcm.tobytes())
    return p

def write(name,w=320,h=180,fps=30,n=8,kind='court'):
    p=OUT/(name+'.mp4'); p.parent.mkdir(parents=True,exist_ok=True)
    wr=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
    if not wr.isOpened(): raise RuntimeError('cv2 VideoWriter failed: '+str(p))
    for i in range(n): wr.write(frame(w,h,kind,i,n))
    wr.release(); return p

REAL_SRC = Path(__file__).resolve().parents[2]/'backend/ml/data/raw/shuttlecock_trajectory/TrackNetV2/Test/match1/video/1_09_06.mp4'
REAL_MODES = [('reencode','mp4','real_baseline'),('vfr','mov','timing_vfr'),('drop','mov','timing_dropped'),
    ('jump','mov','timing_jump'),('longgop','mov','codec_long_gop'),('hdr10','mov','codec_hevc10_hlg'),
    ('audio','mov','container_mov_audio'),('audioonly','mov','no_video_track'),('rot90','mov','rotation_real'),
    ('rot180','mov','rotation_real_landscape_right')]

def real_variants(gen):
    """Real rally footage (1 rally, 3 hits in Python's fixture) re-encoded with controlled
    timing / codec / container. Built by RobustnessGen retime + mp4box.py duppts."""
    import subprocess, sys
    if not gen.exists() or not REAL_SRC.exists(): return []
    out=[]
    for mode,ext,group in REAL_MODES:
        p=OUT/f'real_{mode}.{ext}'
        subprocess.run([str(gen),'retime',str(REAL_SRC),str(p),mode],check=True,stdout=subprocess.DEVNULL)
        out.append((p,group))
    dup=OUT/'real_duppts.mp4'
    subprocess.run([sys.executable,str(Path(__file__).with_name('mp4box.py')),'duppts',str(OUT/'real_reencode.mp4'),str(dup)],
                   check=True,stdout=subprocess.DEVNULL)
    out.append((dup,'timing_duplicate_pts'))
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'empty.mp4').write_bytes(b'')
    manifest=[]
    def add(p,group): manifest.append({'file':p.name,'group':group,'bytes':p.stat().st_size})
    p=write('seed_valid',320,180,30,12); add(p,'seed')
    data=p.read_bytes(); boxes=[]; pos=0
    while pos+8<=len(data):
        size=struct.unpack('>I',data[pos:pos+4])[0]; kind=data[pos+4:pos+8]
        if size<8 or pos+size>len(data): break
        boxes.append((pos,size,kind)); pos+=size
    moov=next((x for x in boxes if x[2]==b'moov'),None); mdat=next((x for x in boxes if x[2]==b'mdat'),None)
    if moov: (OUT/'cut_moov.mp4').write_bytes(data[:moov[0]+max(9,moov[1]//2)])
    else: (OUT/'cut_moov.mp4').write_bytes(data[:max(32,len(data)//2)])
    if mdat: (OUT/'cut_mdat.mp4').write_bytes(data[:mdat[0]+max(9,mdat[1]//2)])
    else: (OUT/'cut_mdat.mp4').write_bytes(data[:max(32,len(data)-max(64,len(data)//3))])
    add(OUT/'cut_moov.mp4','corrupt'); add(OUT/'cut_mdat.mp4','corrupt'); add(OUT/'empty.mp4','corrupt')
    for label,n in [('one_frame',1),('five_frames',5),('half_second',15),('two_seconds',60),('window_minus',7),('one_window',8),('window_plus',9)]: add(write(label,n=n), 'length')
    for w,h,label in [(192,144,'192x144'),(640,360,'640x360'),(1280,720,'1280x720'),(1920,1080,'1920x1080'),(3840,2160,'4k'),(1080,1920,'portrait'),(1918,1078,'odd_even')]: add(write(label,w,h,30,2),'resolution')
    for fps in (24,25,30,50,60,120,240): add(write(f'fps_{fps}',320,180,fps,8),'fps')
    for kind in ('black','white','court','random','shake','zoom','flicker','two_courts','person','far_half','upside'):
        add(write('content_'+kind,kind=kind,n=12),'content')
    gen=Path('/tmp/luna10/gen/release/RobustnessGen')
    if gen.exists():
        import subprocess
        for codec in ('h264','hevc'):
            for rot in (0,90,180,270):
                path=OUT/f'{codec}_rot{rot}.mov'
                subprocess.run([str(gen),str(path),codec,str(rot),'12','30'],check=True)
                add(path,f'codec_{codec}_rotation_{rot}')
    ap=audio_only(); add(ap,'no_video_track')
    for p,g in real_variants(gen): add(p,g)
    missing=[] if gen.exists() else ['all real_* variants (RobustnessGen not built)']
    (OUT/'manifest.json').write_text(json.dumps({'seed':SEED,'clips':manifest,'not_generated':missing},indent=2)+'\n')
    print(f'generated {len(manifest)} clips in {OUT}')
if __name__=='__main__': main()
