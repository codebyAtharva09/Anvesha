# Commands to run on your laptop (Windows)

Open **Command Prompt** (not PowerShell) and run these one by one.

## 1. Go to the project folder
```
G:
cd "G:\SIH ISRO"
```

## 2. Install everything globally (one time)
```
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pytest pyinstaller
```
Optional (only for retraining the CNN on your NVIDIA GPU — pick the CUDA build that matches `nvidia-smi`):
```
python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
```

## 3. Run everything with logs (writes to G:\SIH ISRO\logs and G:\SIH ISRO\results)
```
run_all_on_laptop.bat
```
Takes about 40–80 minutes. When it finishes, tell me and I will read `logs\` and `results\` and update the PPT with your laptop's numbers.

## 4. Try the GUI (any time)
```
run_gui.bat
```
Browser opens at http://127.0.0.1:8765 → pick a scenario → START.

## 5. Optional
```
train_gpu.bat                         REM retrain BeaconNet on the GPU  (log: logs\train_gpu.log)
python tools\train_beaconnet.py --steps 20000 --batch 256 --device auto > logs\07_train_gpu.log 2>&1
packaging\build_exe.bat               REM build dist\ANVESHA\ANVESHA.exe
```
