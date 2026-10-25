"""守門入口（全域 hook 慣例檔）：跑 tests/ 底下所有 test_*.py，任一失敗就 exit 1。"""
import glob, os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
failed = False
for t in sorted(glob.glob(os.path.join(here, "test_*.py"))):
    print("=== %s ===" % os.path.basename(t), flush=True)
    if subprocess.run([sys.executable, t]).returncode != 0:
        failed = True
print("守門：" + ("紅" if failed else "全綠"))
sys.exit(1 if failed else 0)
