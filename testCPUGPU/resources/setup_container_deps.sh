#!/usr/bin/env bash
# Cài thư viện hệ thống còn thiếu để ultralytics/YOLO (cv2) import được
# bên trong container vcd-vision-ai. Chỉ cần chạy 1 lần sau khi container khởi động lại.
#
#   bash setup_container_deps.sh
set -e
docker exec -u 0 vcd-vision-ai sh -c 'apt-get update -qq && apt-get install -y -qq libxcb1 libgl1 libglib2.0-0'
echo "Kiểm tra import:"
docker exec vcd-vision-ai python -c "from ultralytics import YOLO; print('YOLO_IMPORT_OK')"
