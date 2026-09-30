@echo off
REM Full benchmark: 16 scenarios x 4 pipelines x 3 seeds, then ablation. Reports in results\
cd /d "%~dp0"
python -m anvesha bench --seeds 1 2 3 --out results\bench
python -m anvesha ablate --seeds 1 2 3 --out results\ablation
start "" results\bench\benchmark_report.html
