"""守門入口（全域 hook 慣例檔）：跑 tests/ 底下所有 test_*.py，任一失敗就 exit 1。
手動跑：python3 tests/guard_test.py（--no-cache＝全部重跑不看快取；上線前用這個）

★快取（2026-11-15）：慢的測試檔（SLOW_DEPS 有列的）只在「它會讀到的檔案」內容有變時才重跑。
  - 指紋＝相依檔案**內容**的 sha1（不是修改時間），存在 tests/.guard_cache.json（不進 git）。
  - 只記「通過」；紅的永遠重跑。相依範圍用**排除法**：預設整個專案都算，
    只排除確定讀不到的（文件、別支測試、診斷工具）→ 漏列只會多跑，不會假綠。
  - 新的測試檔沒列進 SLOW_DEPS＝每次都跑（安全預設）。
  - 環境（python／playwright 版本、YouTube、訊息伺服器）不在指紋裡：上線前 --no-cache 跑一次。
★順序：快的（靜態規則、golden）先跑；快的就紅了＝先不跑慢的同步測試（省 2 分鐘，修好再跑）。
★結尾會把所有 FAIL 行再列一次（hook 只看最後 15 行，紅的不能被後面的輸出洗掉）。
"""
import fnmatch, glob, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".guard_cache.json")

# 任何測試都讀不到的東西
ALWAYS_SKIP = ["*.pyc", "*.DS_Store", "*.png", "tests/.guard_cache.json"]
# 慢的測試檔 → 它**讀不到**的檔案（其餘全部算相依）
SLOW_DEPS = {
    # 開瀏覽器測同步：讀 index.html、lib/、自己；不讀文件、靜態測試、golden 快照、診斷工具、守門入口
    "test_sync.py": ["*.md", ".gitignore", "tools/*", "tests/guard_test.py", "tests/test_rules.py",
                     "tests/test_golden.py", "tests/golden/*"],
}


def _all_files():
    out = []
    for root, dirs, files in os.walk(PROJ):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), PROJ)
            if not any(fnmatch.fnmatch(rel, pat) for pat in ALWAYS_SKIP):
                out.append(rel)
    return sorted(out)


def fingerprint(test_name, files=None):
    """這支測試的相依指紋；沒列在 SLOW_DEPS 的回傳 None（＝不快取）。"""
    if test_name not in SLOW_DEPS:
        return None
    skip = SLOW_DEPS[test_name]
    h = hashlib.sha1()
    for rel in files if files is not None else _all_files():
        if any(fnmatch.fnmatch(rel, pat) for pat in skip):
            continue
        with open(os.path.join(PROJ, rel), "rb") as f:
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha1(f.read()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def _load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _run(path):
    """跑一支測試：輸出照常即時印出，回傳（exit code, PASS 項數, FAIL 行）。"""
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, encoding="utf-8", errors="replace", env=env)
    passed, fail_lines = 0, []
    for line in p.stdout:
        print(line, end="", flush=True)
        if line.startswith("PASS "): passed += 1
        elif line.startswith("FAIL "): fail_lines.append(line.rstrip("\n"))
    return p.wait(), passed, fail_lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    use_cache = "--no-cache" not in argv
    cache = _load_cache() if use_cache else {}
    files = _all_files()
    tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")),
                   key=lambda t: (os.path.basename(t) in SLOW_DEPS, t))  # 快的先跑
    failed, all_fails, total = [], [], 0
    for path in tests:
        name = os.path.basename(path)
        print("=== %s ===" % name, flush=True)
        if failed and name in SLOW_DEPS:
            print("略過 %s：前面已經紅了，先修好再跑這支慢的" % name, flush=True)
            continue
        fp = fingerprint(name, files)
        hit = cache.get(name) if use_cache and fp else None
        if hit and hit.get("fp") == fp:
            total += hit.get("pass", 0)
            print("PASS %s（相依檔案沒變，沿用上次通過的 %d 項；要重跑加 --no-cache）" % (name, hit.get("pass", 0)), flush=True)
            continue
        t0 = time.time()
        code, passed, fail_lines = _run(path)
        print("（%s：%d 秒）" % (name, time.time() - t0), flush=True)
        total += passed
        if code == 0:
            if fp: cache[name] = {"fp": fp, "pass": passed}
        else:
            failed.append(name); all_fails += fail_lines or ["FAIL %s（沒跑完，exit %d，看上面的錯誤訊息）" % (name, code)]
            cache.pop(name, None)
    try:  # 先組好字串再開檔（開檔會先清空）
        text = json.dumps(cache, ensure_ascii=False, indent=1)
        with open(CACHE, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    for line in all_fails:
        print(line[:300])
    print("守門：" + ("紅（%s）" % "、".join(failed) if failed else "全綠（共 %d 項通過）" % total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
