#!/bin/bash

echo "=== AI Environment Setup Script ==="
PY_VERSION=3.10.9

PY_SHORT=$(echo $PY_VERSION | cut -d. -f1,2)
PY_BIN="/usr/local/bin/python$PY_SHORT"
ENV_PATH="$HOME/Desktop/env"

# ===== SYSTEM UPDATE =====
echo "Updating system..."
sudo apt update -y

# ===== INSTALL DEPENDENCIES =====
echo "Installing dependencies..."
sudo apt install -y build-essential zlib1g-dev \
libncurses5-dev libgdbm-dev libnss3-dev \
libssl-dev libreadline-dev libffi-dev \
libsqlite3-dev wget curl llvm \
libbz2-dev liblzma-dev tk-dev

# ===== DOWNLOAD PYTHON =====
echo "⬇Downloading Python $PY_VERSION..."
cd /tmp
wget https://www.python.org/ftp/python/$PY_VERSION/Python-$PY_VERSION.tgz

if [ ! -f "Python-$PY_VERSION.tgz" ]; then
  echo "Download failed"
  exit 1
fi

# ===== BUILD PYTHON =====
echo "Extracting..."
tar -xf Python-$PY_VERSION.tgz
cd Python-$PY_VERSION

echo "⚙Building Python..."
./configure --enable-optimizations
make -j$(nproc)
sudo make altinstall

# ===== CHECK PYTHON =====
echo "Installed version:"
$PY_BIN --version

# ===== CREATE VENV =====
echo "Creating virtual environment..."
$PY_BIN -m venv $ENV_PATH

source $ENV_PATH/bin/activate

# ===== UPGRADE PIP =====
echo "⬆Upgrading pip..."
pip install --upgrade pip

# ===== INSTALL PYTORCH =====
echo "Installing PyTorch (CUDA 11.8)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# ===== INSTALL REQUIREMENTS =====
echo "Installing additional libraries..."
pip install -r requirements.txt

# ===== CHECK TMUX =====
echo "Checking tmux..."
if ! command -v tmux &> /dev/null
then
  echo "tmux not found"
  read -p "Install tmux? (y/n): " INSTALL_TMUX
  if [ "$INSTALL_TMUX" == "y" ]; then
    sudo apt install tmux -y
  fi
else
  echo "tmux already installed"
fi

# ===== ASK CREATE TMUX =====
if command -v tmux &> /dev/null
then
  read -p "Create new tmux session? (y/n): " CREATE_TMUX
  if [ "$CREATE_TMUX" == "y" ]; then
    tmux new -s ai_training
  fi
fi

# ===== FINAL CHECK =====
echo "Testing PyTorch GPU..."
python - <<EOF
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
EOF

echo "Setup complete!"