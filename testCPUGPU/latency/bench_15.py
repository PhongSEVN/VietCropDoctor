import time, json, statistics
import requests
URL="http://localhost:8006/orchestrate"; IMG="testimg.jpg"; N=15
stages=["vision_ms","retrieval_ms","llm_ms","total_ms"]
acc={s:[] for s in stages}
fout=open("bench15_rows.jsonl","w")
for i in range(N):
    with open(IMG,"rb") as f:
        r=requests.post(URL,files={"image":("t.jpg",f,"image/jpeg")},data={"query":"Bệnh này xử lý thế nào?"},timeout=180)
    lm=r.json().get("latency_ms",{})
    for s in stages: acc[s].append(lm.get(s,float("nan")))
    fout.write(json.dumps(lm)+"\n"); fout.flush()
    print("iter %d: %s"%(i,json.dumps(lm)),flush=True)
fout.close()
def p95(xs):
    xs=sorted(xs); return xs[int(round(0.95*(len(xs)-1)))]
print("\n=== LATENCY n=%d (mean / p95) ==="%N,flush=True)
res={}
for s in stages:
    m=statistics.mean(acc[s]); p=p95(acc[s]); res[s]={"mean":round(m,1),"p95":round(p,1)}
    print("%-14s mean=%9.1f  p95=%9.1f"%(s,m,p),flush=True)
json.dump(res,open("bench15_result.json","w"),indent=2)
print("SAVED",flush=True)
