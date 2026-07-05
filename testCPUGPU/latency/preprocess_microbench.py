"""Micro-benchmark bước tiền xử lý ảnh (decode + Resize224 + ToTensor + Normalize).
Chạy BÊN TRONG container vcd-vision-ai (có sẵn torch/PIL + module preprocessing).

    docker cp preprocess_microbench.py vcd-vision-ai:/tmp/
    docker exec vcd-vision-ai python /tmp/preprocess_microbench.py

Sửa IMG cho đúng 1 ảnh test bất kỳ trong container.
"""
import io, time, statistics, importlib.util
from PIL import Image

IMG = "/tmp/test/Cafe_benh_dom_rong/IMG_2268_2_JPG.rf.6cfbec6facd17cdf1485b93b99b158fc.jpg"

spec = importlib.util.spec_from_file_location("pp", "/service/app/cv/preprocessing.py")
pp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pp)
tf = pp.DEFAULT_TRANSFORM

b = open(IMG, "rb").read()
for _ in range(10):  # warmup
    img = Image.open(io.BytesIO(b)).convert("RGB"); tf(img)

xs = []
for _ in range(200):
    t0 = time.perf_counter()
    img = Image.open(io.BytesIO(b)).convert("RGB"); tf(img)
    xs.append((time.perf_counter() - t0) * 1000)
xs.sort()
print("preprocess per-image ms: mean=%.2f p95=%.2f min=%.2f"
      % (statistics.mean(xs), xs[int(0.95 * 199)], xs[0]))
print("Lưu ý: ensemble decode+transform 1 lần MỖI mô hình torch (4) + YOLO decode riêng;"
      " con số trên là 1 lần tiền xử lý, đã nằm trong vision_ms.")
