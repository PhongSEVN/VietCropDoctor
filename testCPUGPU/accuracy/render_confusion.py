"""Render ma trận nhầm lẫn ensemble từ ens_confusion.csv + canon.json.
Chạy TRÊN HOST (cần matplotlib + numpy). Lấy 2 file đầu vào từ container sau khi
aggregate.py đã chạy:

    docker cp vcd-vision-ai:/tmp/ens_confusion.csv ./
    docker cp vcd-vision-ai:/tmp/canon.json ./
    python render_confusion.py

Đầu ra: confusion_matrix_ensemble.png
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

canon = json.load(open("canon.json", encoding="utf-8"))
cm = np.loadtxt("ens_confusion.csv", delimiter=",", dtype=int)
n = len(canon)
cmn = cm.astype(float) / cm.sum(1, keepdims=True).clip(min=1)

acc = np.trace(cm) / cm.sum()
fig, ax = plt.subplots(figsize=(13, 11))
im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
ax.set_xticks(range(n)); ax.set_yticks(range(n))
ax.set_xticklabels(canon, rotation=90, fontsize=6)
ax.set_yticklabels(canon, fontsize=6)
ax.set_xlabel("Nhãn dự đoán (Predicted)", fontsize=11)
ax.set_ylabel("Nhãn thực tế (True)", fontsize=11)
ax.set_title("Ma trận nhầm lẫn - Ensemble (test set)\nAccuracy=%.4f" % acc, fontsize=12)
for i in range(n):
    for j in range(n):
        v = cm[i, j]
        if v > 0:
            ax.text(j, i, str(v), ha="center", va="center", fontsize=5,
                    color="white" if cmn[i, j] > 0.5 else "black")
fig.colorbar(im, fraction=0.046, pad=0.04, label="Tỷ lệ chuẩn hóa theo hàng")
plt.tight_layout()
plt.savefig("confusion_matrix_ensemble.png", dpi=150, bbox_inches="tight")
print("SAVED confusion_matrix_ensemble.png  acc=%.4f" % acc)
