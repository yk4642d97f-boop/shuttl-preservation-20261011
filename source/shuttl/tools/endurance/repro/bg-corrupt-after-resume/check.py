import struct, sys, numpy as np
def bgs(path):
    b=open(path,'rb').read(); o=6; fl=struct.unpack_from('<I',b,o)[0]; o+=4+fl; nl=struct.unpack_from('<I',b,o)[0]; o+=4+nl; out=[]
    while o<len(b):
        k=b[o]; ln=struct.unpack_from('<I',b,o+1)[0]; p=b[o+13:o+13+ln]; o+=13+ln
        if k==1 and p[0]==1: out.append(p[1:])
    return out
def plan(bg):
    q=8; n=struct.unpack_from('<I',bg,4)[0]; r=[]
    for i in range(n):
        s,w,h=struct.unpack_from('<III',bg,q); q+=12; r.append(np.frombuffer(bg,np.uint8,w*h*3,q).reshape(h,w,3)); q+=w*h*3
    return r
a=plan(bgs(sys.argv[1])[-1]); B=bgs(sys.argv[2]); b=plan(B[-1])
bad=[i for i,(x,y) in enumerate(zip(a,b)) if not np.array_equal(x,y)]
print(f"  bg records in resumed file: {len(B)}; segments changed vs clean plan: {bad}",
      *(f"seg {i}: {(np.abs(a[i].astype(int)-b[i].astype(int)).max(axis=2)>0).mean():.3%} px, zero rows {sorted(set(np.nonzero(b[i].max(axis=2)==0)[0]))[:3]}.." for i in bad))
