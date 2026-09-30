@echo off
REM ============================================================
REM  ANVESHA - full verification run on this laptop.
REM  Everything is logged into  logs\  and  results\  inside this folder.
REM ============================================================
cd /d "%~dp0"
if not exist logs mkdir logs

echo [1/6] Environment info
python --version > logs\00_env.log 2>&1
python -c "import platform,os;print(platform.platform());print('cpus',os.cpu_count())" >> logs\00_env.log 2>&1
nvidia-smi >> logs\00_env.log 2>&1

echo [2/6] Unit tests
python -m pytest -q > logs\01_tests.log 2>&1

echo [3/6] Single demo run with automatic report
python -m anvesha run --scenario M_combined --pipeline anvesha --seed 1 --out results\runs\demo_M_combined > logs\02_demo_run.log 2>&1

echo [4/6] Benchmark: 16 scenarios x 4 pipelines x 3 seeds (15-40 min)
python -m anvesha bench --seeds 1 2 3 --out results\bench > logs\03_bench.log 2>&1

echo [5/6] Ablation study (20-40 min)
python -m anvesha ablate --seeds 1 2 3 --scenarios A_clean E_jitter F_platform G_fog J_fast K_occlusion M_combined N_worst D_saltpepper O_distractors --out results\ablation > logs\04_ablation.log 2>&1

echo [6/6] Benchmark-2 video rehearsal (generate 10 s 2000x2000 video, then run video mode)
python -m anvesha make-video --scenario M_combined --seconds 10 --seed 7 --out results\videos\M_combined_10s.mp4 > logs\05_make_video.log 2>&1
python -m anvesha video --input results\videos\M_combined_10s.mp4 --truth results\videos\M_combined_10s.truth.csv --out results\video_M10 > logs\06_video_mode.log 2>&1

echo Done. Logs in %~dp0logs  -  reports in %~dp0results
start "" results\bench\benchmark_report.html
pause
