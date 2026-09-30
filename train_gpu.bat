@echo off
REM Retrain BeaconNet on this PC's NVIDIA GPU (falls back to CPU if CUDA is unavailable).
REM Needs: pip install torch --index-url https://download.pytorch.org/whl/cu124  (pick the CUDA build matching your driver)
cd /d "%~dp0"
if not exist logs mkdir logs
python tools\train_beaconnet.py --steps 20000 --batch 256 --device auto > logs\07_train_gpu.log 2>&1
pause
