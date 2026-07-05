import time, json, statistics, sys
import requests

URL="http://localhost:8006/orchestrate"
IMG="testimg.jpg"
N=50; WARM=3

def call():
    with open(IMG,"rb") as f:
        files={"image":("testimg.jpg",f,"image/jpeg")}
        data={"query":"Bệnh này xử lý thế nào?"}
        t0=time.perf_counter()
        r=requests.post(URL,files=files,data=data,timeout=120)
        wall=(time.perf_counter()-t0)*1000
    r.raise_for_status()
    j=r.json()
    return j.get("latency_ms",{}), wall

# warm-up
for i in range(WARM):
    lm,w=call(); print("warmup %d total=%.0f keys=%s"%(i,w,list(lm.keys())),flush=True)

stages=["vision_ms","retrieval_ms","llm_ms","total_ms"]
acc={s:[] for s in stages}; wall_list=[]
for i in range(N):
    lm,w=call(); wall_list.append(w)
    for s in stages: acc[s].append(lm.get(s,float("nan")))
    if i%10==0: print("iter %d total_ms=%.0f"%(i,lm.get("total_ms",-1)),flush=True)

def p95(xs):
    xs=sorted(xs); k=int(round(0.95*(len(xs)-1))); return xs[k]

print("\nLATENCY (n=%d)"%N,flush=True)
print("%-14s%12s%12s"%("stage","mean_ms","p95_ms"),flush=True)
res={}
for s in stages:
    xs=acc[s]; m=statistics.mean(xs); p=p95(xs); res[s]=(m,p)
    print("%-14s%12.1f%12.1f"%(s,m,p),flush=True)
mw=statistics.mean(wall_list); pw=p95(wall_list)
print("%-14s%12.1f%12.1f"%("wall_client",mw,pw),flush=True)
json.dump({s:{"mean":res[s][0],"p95":res[s][1]} for s in stages}|{"wall_client":{"mean":mw,"p95":pw}},
          open("bench_result.json","w"),indent=2)
print("SAVED bench_result.json",flush=True)
