import os, glob, json
import numpy as np
TEST="/tmp/test"
CANON=sorted([d for d in os.listdir(TEST) if os.path.isdir(os.path.join(TEST,d))])
cidx={c:i for i,c in enumerate(CANON)}
imgs=[]; ytrue=[]
for c in CANON:
    for p in glob.glob(os.path.join(TEST,c,"*")):
        if p.lower().endswith((".jpg",".jpeg",".png")):
            imgs.append(p); ytrue.append(cidx[c])
N=len(imgs); print("imgs=%d"%N,flush=True)
from ultralytics import YOLO
ym=YOLO("/tmp/m_yolo.pt"); names=ym.names
cn_y=[names[i] for i in range(len(names))]
perm=np.array([cidx[n] for n in cn_y])
Py=np.zeros((N,len(CANON)),dtype=np.float32); B=16
for s in range(0,N,B):
    rr=ym.predict(imgs[s:s+B],imgsz=224,verbose=False)
    for j,r in enumerate(rr): Py[s+j][perm]=r.probs.data.cpu().numpy()
    if s%320==0: print("  YOLO: %d/%d"%(s,N),flush=True)
np.save("/tmp/probs_YOLO.npy",Py)
print("[done] YOLO saved",flush=True)
