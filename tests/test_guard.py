"""守門入口自己的規則（2026-11-15 守門快取＋縮時）：快取不能假綠、紅的不能被洗掉。
驗行為不驗字串：在暫存資料夾蓋一個假專案，真的跑 guard_test.main()，看同步測試有沒有被執行。"""
import contextlib, fnmatch, importlib.util, io, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name, flush=True)
    if not cond: fails.append(name)

spec = importlib.util.spec_from_file_location("guard_under_test", os.path.join(ROOT, "tests", "guard_test.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
REAL = (g.HERE, g.PROJ, g.CACHE)

def write(root, rel, text, mode="w"):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, encoding="utf-8") as f: f.write(text)

tmp = tempfile.mkdtemp(); proj = os.path.join(tmp, "proj"); counter = os.path.join(tmp, "ran.log")  # 計數檔放專案外
def sync_src(body):  # 假的同步測試：每被執行一次就在計數檔記一筆
    return "import sys\nopen(%r, 'a').write('x')\n%s\n" % (counter, body)
def ran():
    return len(open(counter).read()) if os.path.exists(counter) else 0
def run(*argv):
    g.HERE, g.PROJ, g.CACHE = os.path.join(proj, "tests"), proj, os.path.join(proj, "tests", ".guard_cache.json")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = g.main(list(argv))
    return code, buf.getvalue()

try:
    for rel, text in [("index.html", "v1"), ("lib/x.min.js", "lib1"), ("使用步驟.md", "doc1"), ("tools/t.py", "tool1"),
                      ("tests/test_rules.py", "print('PASS r')"), ("tests/test_sync.py", sync_src("print('PASS a'); print('PASS b')"))]:
        write(proj, rel, text)

    code, out = run()
    check("第一次：同步測試有跑、全綠、報總通過項數", code == 0 and ran() == 1 and "守門：全綠（共 3 項通過）" in out)
    code, out = run()
    check("相依檔案沒變：同步測試不重跑、仍全綠、總項數不變少", code == 0 and ran() == 1 and "守門：全綠（共 3 項通過）" in out)
    write(proj, "使用步驟.md", "doc2"); write(proj, "tools/t.py", "tool2"); write(proj, "tests/test_rules.py", "print('PASS r')  # 改過")
    code, out = run()
    check("只改文件／工具／靜態測試：同步測試不重跑", code == 0 and ran() == 1)
    n = ran()
    for rel, text, why in [("index.html", "v2", "網頁"), ("lib/x.min.js", "lib2", "程式庫"), ("new.js", "new", "新加的檔案（排除法：沒列的都算）")]:
        write(proj, rel, text); code, out = run(); n += 1
        check("改了%s：同步測試一定重跑" % why, code == 0 and ran() == n)
    write(proj, "tests/test_sync.py", "# 改過\n", "a"); code, out = run(); n += 1
    check("改了同步測試本身：一定重跑", code == 0 and ran() == n)
    os.utime(os.path.join(proj, "index.html"), (1, 1)); code, out = run()
    check("只有修改時間變、內容沒變：不重跑（指紋看內容）", code == 0 and ran() == n)
    code, out = run("--no-cache"); n += 1
    check("--no-cache：一定重跑", code == 0 and ran() == n)

    # 紅的不快取、不會被洗掉
    write(proj, "tests/test_sync.py", sync_src("print('FAIL 壞掉的項目'); sys.exit(1)"))
    code, out = run(); n += 1
    last = out.strip().splitlines()[-2:]
    check("同步測試紅：守門紅，結尾把 FAIL 行再列一次", code == 1 and ran() == n and last[0] == "FAIL 壞掉的項目" and last[1].startswith("守門：紅"))
    code, out = run(); n += 1
    check("紅的不記快取：下次照樣重跑", code == 1 and ran() == n)
    write(proj, "tests/test_sync.py", sync_src("raise RuntimeError('沒跑完')"))
    code, out = run(); n += 1
    check("同步測試當掉（沒印 FAIL）：守門也紅、結尾有 FAIL 行", code == 1 and out.strip().splitlines()[-2].startswith("FAIL test_sync.py"))
    write(proj, "tests/test_sync.py", sync_src("print('PASS a')"))
    code, out = run(); n += 1
    check("修好後重跑變綠", code == 0 and ran() == n)

    # 靜態測試先跑，紅了就略過慢的
    write(proj, "tests/test_rules.py", "import sys; print('FAIL 靜態壞了'); sys.exit(1)")
    write(proj, "index.html", "v3")
    code, out = run()
    check("靜態測試紅：同步測試略過不跑、守門紅", code == 1 and ran() == n and "略過 test_sync.py" in out and out.index("test_rules.py") < out.index("=== test_sync.py"))
    write(proj, "tests/test_rules.py", "print('PASS r')")
    code, out = run(); n += 1
    check("靜態修好：被略過的同步測試一定補跑（略過不算通過）", code == 0 and ran() == n)
finally:
    g.HERE, g.PROJ, g.CACHE = REAL
    shutil.rmtree(tmp, ignore_errors=True)

# 真專案的設定
check("沒列在慢測試清單的測試不快取（每次都跑）", g.fingerprint("test_rules.py") is None and g.fingerprint("test_golden.py") is None and g.fingerprint("test_guard.py") is None)
check("只有同步測試走快取", sorted(g.SLOW_DEPS) == ["test_sync.py"])
skip = g.SLOW_DEPS["test_sync.py"] + g.ALWAYS_SKIP
need = ["index.html", "tests/test_sync.py"] + [f for f in g._all_files() if f.startswith("lib/")]
check("同步測試的相依一定含網頁、程式庫、它自己", len(need) >= 4 and all(f in g._all_files() and not any(fnmatch.fnmatch(f, p) for p in skip) for f in need))
ign = subprocess.run(["git", "check-ignore", "-q", "tests/.guard_cache.json"], cwd=ROOT).returncode == 0
tracked = subprocess.run(["git", "ls-files", "tests/.guard_cache.json"], cwd=ROOT, stdout=subprocess.PIPE).stdout.strip()
check("快取檔不進 git", ign and not tracked)
sys.exit(1 if fails else 0)
