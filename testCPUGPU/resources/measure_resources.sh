#!/usr/bin/env bash
#
#   bash measure_resources.sh
#
# Yêu cầu: docker, nvidia-smi (nếu có GPU NVIDIA).
set -u

echo "===================== HOST / VM ====================="
echo -n "Host cores (Docker VM): "; docker exec vcd-vision-ai nproc 2>/dev/null
docker exec vcd-vision-ai sh -c 'grep MemTotal /proc/meminfo' 2>/dev/null

echo ""
echo "===================== GPU (3 mẫu cách 3s) ====================="
for i in 1 2 3; do
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null \
    || echo "nvidia-smi không khả dụng"
  sleep 3
done

echo ""
echo "===================== docker stats (snapshot) ====================="
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" \
  | grep -E "vcd-ollama|vcd-vision-ai|vcd-rag-engine|vcd-orchestrator|vcd-qdrant|vcd-postgres"

echo ""
echo "===================== Tổng RAM tất cả container vcd- ====================="
docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" $(docker ps --format "{{.Names}}" | grep vcd-) \
  | python -c "
import sys, re
tot = 0; rows = []
for line in sys.stdin:
    p = line.split()
    if len(p) < 2: continue
    m = re.match(r'([\d.]+)(MiB|GiB)', p[1])
    if m:
        v = float(m.group(1)) * (1024 if m.group(2) == 'GiB' else 1)
        tot += v; rows.append((v, p[0]))
rows.sort(reverse=True)
for v, n in rows[:8]: print('%-20s %7.0f MiB' % (n, v))
print('--- TOTAL: %.0f MiB = %.2f GiB ---' % (tot, tot / 1024))
"

echo ""
echo "===================== Disk (docker) ====================="
docker system df

echo ""
echo "===================== Model Ollama đang chạy ====================="
docker exec vcd-ollama ollama ps 2>/dev/null
docker exec vcd-ollama ollama list 2>/dev/null
