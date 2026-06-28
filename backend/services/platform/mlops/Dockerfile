FROM python:3.11-slim

WORKDIR /workspace

# Install CPU-only PyTorch; swap index URL for CUDA builds
RUN pip install --no-cache-dir \
      torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
      timm>=1.0.0 \
      mlflow>=2.11.0 \
      scikit-learn>=1.3.0 \
      pyyaml>=6.0 \
      Pillow>=10.0.0 \
      numpy>=1.24.0

# Source code is bind-mounted at runtime
CMD ["python", "--version"]
