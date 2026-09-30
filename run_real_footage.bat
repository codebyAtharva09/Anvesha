@echo off
REM Real-footage check: run the Benchmark-2 video tracker on your own clip (phone video of a moving LED / laser dot).
REM Usage:  run_real_footage.bat my_clip.mp4 [beacon_size_px]
cd /d "%~dp0"
if "%~1"=="" (echo Usage: run_real_footage.bat my_clip.mp4 [beacon_size_px] & exit /b 1)
set BS=%~2
if "%BS%"=="" set BS=12
if not exist logs mkdir logs
python -m anvesha video --input "%~1" --out results\real_footage --beacon-size %BS% > logs\08_real_footage.log 2>&1
type results\real_footage\video_summary.json
start "" results\real_footage\track_preview.png
