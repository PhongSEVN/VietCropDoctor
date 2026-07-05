import os, glob, json, importlib.util
import numpy as np, torch
import torch.nn as nn
import torchvision.transforms as T
from PIL import Image
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

torch.set_num_threads(os.cpu_count() or 8)
spec=importlib.util.spec_from_file_location("arch","/service/app/cv/architectures.py")
arch=importlib.util.module_from_spec(spec); spec.loader.exec_module(arch)

TEST="/tmp/test"
CANON=sorted([d for d in os.listdir(TEST) if os.path.isdir(os.path.join(TEST,d))])
cidx={c:i for i,c in enumerate(CANON)}
imgs=[]; ytrue=[]
for c in CANON:
    for p in glob.glob(os.path.join(TEST,c,"*")):
        if p.lower().endswith((".jpg",".jpeg",".png")):
            imgs.append(p); ytrue.append(cidx[c])
ytrue=np.array(ytrue); N=len(imgs)
print("test images=%d classes=%d"%(N,len(CANON)),flush=True)

tf=T.Compose([T.Resize((224,224)),T.ToTensor(),T.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])])
def perm_for(cn): return np.array([cidx[n] for n in cn])
probs={}

# 3 torchvision CNNs via serving build_architecture
TORCH=[("MobileNetV3","mobilenetv3","/tmp/m_mobilenetv3.pth"),
       ("ResNet50","resnet50","/tmp/m_resnet50.pth"),
       ("EfficientNet-B0","efficientnet_b0","/tmp/m_efficientb0.pth")]
def cache_path(name): return "/tmp/probs_%s.npy"%name.replace("/","_")
for name,akey,path in TORCH:
    cp=cache_path(name)
    if os.path.exists(cp):
        probs[name]=np.load(cp); print("[cached] %s"%name,flush=True); continue
    ck=torch.load(path,map_location="cpu",weights_only=False)
    sd=ck["model_state_dict"]; nc=ck.get("num_classes",len(CANON)); cn=ck.get("class_names",CANON)
    m=arch.build_architecture(akey,nc); m.load_state_dict(sd); m.eval()
    perm=perm_for(cn); P=np.zeros((N,len(CANON)),dtype=np.float32); B=32
    with torch.no_grad():
        for s in range(0,N,B):
            batch=torch.stack([tf(Image.open(p).convert("RGB")) for p in imgs[s:s+B]])
            pr=torch.softmax(m(batch),1).cpu().numpy()
            P[s:s+B][:,perm]=pr
            if s%640==0: print("  %s: %d/%d"%(name,s,N),flush=True)
    probs[name]=P; np.save(cp,P); print("[done] %s"%name,flush=True)

# ViT: HuggingFace ViTForPlantDisease wrapper (matches training)
from transformers import ViTModel, ViTConfig
class ViTForPlantDisease(nn.Module):
    def __init__(self, num_classes, dropout=0.3):
        super().__init__()
        self.backbone = ViTModel(ViTConfig())  # vit-base-patch16-224 arch, random init (overwritten)
        h = self.backbone.config.hidden_size
        self.classifier = nn.Sequential(
            nn.LayerNorm(h), nn.Linear(h,256), nn.GELU(), nn.Dropout(dropout), nn.Linear(256,num_classes))
    def forward(self, x):
        out = self.backbone(pixel_values=x)
        return self.classifier(out.last_hidden_state[:,0,:])

ck=torch.load("/tmp/m_vit.pth",map_location="cpu",weights_only=False)
sd=ck["model_state_dict"]; nc=ck.get("num_classes",len(CANON)); cn=ck.get("class_names",CANON)
# Remap OLD HF naming (encoder.layer.N.*) -> transformers 5.x naming (layers.N.*)
def remap_vit(sd):
    rep=[(".encoder.layer.",".layers."),
         (".attention.attention.query.",".attention.q_proj."),
         (".attention.attention.key.",".attention.k_proj."),
         (".attention.attention.value.",".attention.v_proj."),
         (".attention.output.dense.",".attention.o_proj."),
         (".intermediate.dense.",".mlp.fc1."),
         (".output.dense.",".mlp.fc2.")]
    out={}
    for k,v in sd.items():
        nk=k
        if nk.startswith("backbone.encoder.layer."):
            for a,b in rep: nk=nk.replace(a,b)
        out[nk]=v
    return out
sd=remap_vit(sd)
mv=ViTForPlantDisease(nc)
res=mv.load_state_dict(sd,strict=False)
miss=[k for k in res.missing_keys if not k.startswith("backbone.pooler")]
unexp=[k for k in res.unexpected_keys if not k.startswith("backbone.pooler")]
print("ViT load: missing(non-pooler)=%d unexpected(non-pooler)=%d"%(len(miss),len(unexp)),flush=True)
if miss[:5]: print("  miss:",miss[:5],flush=True)
if unexp[:5]: print("  unexp:",unexp[:5],flush=True)
assert len(miss)==0 and len(unexp)==0, "ViT key mismatch -> would give wrong metrics"
mv.eval()
if os.path.exists(cache_path("ViT")):
    probs["ViT"]=np.load(cache_path("ViT")); print("[cached] ViT",flush=True)
else:
    perm=perm_for(cn); P=np.zeros((N,len(CANON)),dtype=np.float32); B=32
    with torch.no_grad():
        for s in range(0,N,B):
            batch=torch.stack([tf(Image.open(p).convert("RGB")) for p in imgs[s:s+B]])
            pr=torch.softmax(mv(batch),1).cpu().numpy()
            P[s:s+B][:,perm]=pr
            if s%640==0: print("  ViT: %d/%d"%(s,N),flush=True)
    probs["ViT"]=P; np.save(cache_path("ViT"),P); print("[done] ViT",flush=True)

# --- YOLOv8s-cls ---
from ultralytics import YOLO
ym=YOLO("/tmp/m_yolo.pt"); names=ym.names
cn_y=[names[i] for i in range(len(names))]; perm=perm_for(cn_y)
Py=np.zeros((N,len(CANON)),dtype=np.float32); B=64
for s in range(0,N,B):
    rr=ym.predict(imgs[s:s+B],imgsz=224,verbose=False)
    for j,r in enumerate(rr): Py[s+j][perm]=r.probs.data.cpu().numpy()
    if s%640==0: print("  YOLO: %d/%d"%(s,N),flush=True)
probs["YOLO"]=Py; np.save(cache_path("YOLO"),Py); print("[done] YOLO",flush=True)

def metrics(yp):
    return dict(acc=float(accuracy_score(ytrue,yp)),
        precision=float(precision_score(ytrue,yp,average="macro",zero_division=0)),
        recall=float(recall_score(ytrue,yp,average="macro",zero_division=0)),
        f1=float(f1_score(ytrue,yp,average="macro",zero_division=0)))

out={name:metrics(P.argmax(1)) for name,P in probs.items()}
W={"MobileNetV3":0.8975,"ResNet50":0.8775,"EfficientNet-B0":0.8405,"ViT":0.9046,"YOLO":0.9749}
tot=sum(W.values())
ens=np.zeros((N,len(CANON)))
for name,P in probs.items(): ens+=(W[name]/tot)*P
yp_ens=ens.argmax(1); out["Ensemble"]=metrics(yp_ens)

print("",flush=True)
print("RESULTS (test set, macro avg)",flush=True)
print("%-16s%10s%10s%11s%9s"%("Model","Accuracy","Macro-F1","Precision","Recall"),flush=True)
for nm in ["ResNet50","YOLO","ViT","MobileNetV3","EfficientNet-B0","Ensemble"]:
    m=out[nm]
    print("%-16s%10.4f%10.4f%11.4f%9.4f"%(nm,m["acc"],m["f1"],m["precision"],m["recall"]),flush=True)

json.dump(out,open("/tmp/eval_metrics.json","w"),indent=2)
np.savetxt("/tmp/ens_confusion.csv",confusion_matrix(ytrue,yp_ens),fmt="%d",delimiter=",")
json.dump(CANON,open("/tmp/canon.json","w"),ensure_ascii=False)
print("SAVED metrics+confusion",flush=True)
