@echo off
REM Benchmark-2 mode: run the coarse-pointing chain on an evaluator .mp4 (PTZ camera bypassed)
REM usage: run_video.bat path\to\video.mp4 [truth.csv]
cd /d "%~dp0"
if "%~2"=="" (python -m anvesha video --input "%~1" --out results\video) else (python -m anvesha video --input "%~1" --truth "%~2" --out results\video)
