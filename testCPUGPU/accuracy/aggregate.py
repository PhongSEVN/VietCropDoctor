import os, glob, json
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
TEST="/tmp/test"
CANON=sorted([d for d in os.listdir(TEST) if os.path.isdir(os.path.join(TEST,d))])
cidx={c:i for i,c in enumerate(CANON)}
imgs=[]; ytrue=[]
for c in CANON:
    for p in glob.glob(os.path.join(TEST,c,"*")):
        if p.lower().endswith((".jpg",".jpeg",".png")):
            imgs.append(p); ytrue.append(cidx[c])
ytrue=np.array(ytrue); N=len(imgs)
print("imgs=%d classes=%d"%(N,len(CANON)),flush=True)

NAMES=["MobileNetV3","ResNet50","EfficientNet-B0","ViT","YOLO"]
probs={}
for nm in NAMES:
    f="/tmp/probs_%s.npy"%nm.replace("/","_")
    P=np.load(f); assert P.shape==(N,len(CANON)), (nm,P.shape)
    probs[nm]=P
    print("loaded %s %s"%(nm,P.shape),flush=True)

def metrics(yp):
    return dict(acc=float(accuracy_score(ytrue,yp)),
        precision=float(precision_score(ytrue,yp,average="macro",zero_division=0)),
        recall=float(recall_score(ytrue,yp,average="macro",zero_division=0)),
        f1=float(f1_score(ytrue,yp,average="macro",zero_division=0)))

out={nm:metrics(P.argmax(1)) for nm,P in probs.items()}
W={"MobileNetV3":0.8975,"ResNet50":0.8775,"EfficientNet-B0":0.8405,"ViT":0.9046,"YOLO":0.9749}
tot=sum(W.values())
ens=np.zeros((N,len(CANON)))
for nm,P in probs.items(): ens+=(W[nm]/tot)*P
yp_ens=ens.argmax(1); out["Ensemble"]=metrics(yp_ens)

print("",flush=True)
print("=== RESULTS (test set, macro avg) ===",flush=True)
print("%-16s%10s%10s%11s%9s"%("Model","Accuracy","Macro-F1","Precision","Recall"),flush=True)
for nm in ["ResNet50","YOLO","ViT","MobileNetV3","EfficientNet-B0","Ensemble"]:
    m=out[nm]
    print("%-16s%10.4f%10.4f%11.4f%9.4f"%(nm,m["acc"],m["f1"],m["precision"],m["recall"]),flush=True)
print("",flush=True)
print("normalized weights:",{k:round(W[k]/tot,4) for k in W},flush=True)

json.dump(out,open("/tmp/eval_metrics.json","w"),indent=2)
np.savetxt("/tmp/ens_confusion.csv",confusion_matrix(ytrue,yp_ens),fmt="%d",delimiter=",")
json.dump(CANON,open("/tmp/canon.json","w"),ensure_ascii=False)
print("SAVED metrics+confusion",flush=True)
