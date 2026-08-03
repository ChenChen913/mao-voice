# -*- coding: utf-8 -*-
"""多 Agent 编排工具：拆任务 -> 派发 Claude Code / Hermes -> 收集结果 -> 审查。

用法:
  python orchestrate.py             # 按 tasks.json 派发全部子任务（真实调用 Agent，会产生费用）
  python orchestrate.py --report    # 只分析已有执行结果（免费，不调用 Agent）
  python orchestrate.py --list      # 列出任务配置
  python orchestrate.py --noop      # 只打印将执行的命令，不真正运行（免费）
  python orchestrate.py --only=任务名[,任务名]

任务契约（tasks.json）:
  name         任务名
  workdir      独立工作区（相对本项目根目录）
  agent        claude | hermes
  prompt_file  工作区内的任务说明文件（如 TASK.md）
  timeout      单任务超时秒数（默认 600）
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"

DEFAULT_PROMPT = (
    "请先通读当前工作目录下的 {prompt}，严格按其中要求完成任务并实现交付物。"
    "只允许创建/修改当前工作目录内的文件，不要执行破坏性命令。"
    "完成后用一句话总结你做了什么。"
)


def load_tasks(path=BASE / "tasks.json"):
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data.get("tasks", [])


def build_command(task, prompt):
    agent = task.get("agent")
    if not isinstance(agent, str) or agent not in ("claude", "hermes"):
        raise ValueError(
            f"tasks.json 中任务 \"{task.get('name', '?')}\" 的 agent 字段无效: {agent!r}，"
            f"必须为 'claude' 或 'hermes'"
        )
    if agent == "claude":
        cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--output-format", "json"]
        return cmd
    if agent == "hermes":
        return ["hermes", "chat", "-q", prompt, "-Q", "--yolo"]
    raise ValueError("未知 agent: " + str(task["agent"]))


def result_path(task):
    if task["agent"] == "claude":
        return RESULTS / (task["name"] + ".claude.json")
    return RESULTS / (task["name"] + ".hermes.txt")


def run_agent(task):
    workdir = (BASE / task["workdir"]).resolve()
    # v5.11：防越界——任务工作目录必须落在项目根内
    if not str(workdir).startswith(str(BASE.resolve())):
        raise ValueError("任务工作目录越界: {}".format(workdir))
    workdir.mkdir(parents=True, exist_ok=True)
    prompt = DEFAULT_PROMPT.format(prompt=task.get("prompt_file", "TASK.md"))
    cmd = build_command(task, prompt)
    timeout = task.get("timeout", 600)
    out_file = result_path(task)
    RESULTS.mkdir(exist_ok=True)
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, timeout=timeout)
        # stdout 写入主结果文件（保持 JSON 等格式纯净）；stderr 单独存档，避免污染
        out_file.write_bytes(proc.stdout)
        if proc.stderr:
            (RESULTS / (task["name"] + ".stderr.txt")).write_bytes(proc.stderr)
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        msg = "TIMEOUT after {}s".format(timeout)
        error_file = RESULTS / (task["name"] + ".timeout.txt")
        error_file.write_text(msg, encoding="utf-8")
        # 只写失败标记文件，绝不污染主结果文件（保持 JSON/纯输出格式一致）
    except OSError as e:  # v5.11：FileNotFoundError 之外还覆盖 PermissionError 等
        ok = False
        msg = "命令不可用: " + str(e)
        error_file = RESULTS / (task["name"] + ".error.txt")
        error_file.write_text(msg, encoding="utf-8")
    elapsed = time.time() - started
    return {"name": task["name"], "agent": task["agent"], "ok": ok,
            "elapsed_sec": round(elapsed, 1), "output": str(out_file)}


def analyze_claude(path):
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return {"ok": False, "cost_usd": 0, "error": "解码失败（非 UTF-8）"}
        data = json.loads(text)
        raw_result = data.get("result")
        result_snippet = raw_result[:120] if isinstance(raw_result, str) else str(raw_result)[:120]
        return {
            "ok": not data.get("is_error", False),
            "cost_usd": round(data.get("total_cost_usd", 0), 4),
            "duration_ms": data.get("duration_ms"),
            "result": result_snippet,
        }
    except Exception as e:
        return {"ok": False, "cost_usd": 0, "error": str(e)}


def analyze_hermes(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        session = ""
        for line in reversed(text.splitlines()):
            if line.startswith("session_id:"):
                session = line.strip()
                break
        return {"ok": path.stat().st_size > 0, "session": session, "size": path.stat().st_size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def find_results(task):
    """优先 results/<name>.*，兼容旧版放在工作区内的 claude_result.json / hermes_result.txt"""
    # 跳过 .timeout.txt / .error.txt / .stderr.txt 等标记文件，只匹配真正的结果文件
    _SKIP_NAMES = (".timeout.txt", ".error.txt", ".stderr.txt")
    cand = [
        p for p in RESULTS.glob(task["name"] + ".*")
        if not p.name.endswith(_SKIP_NAMES)
    ] if RESULTS.exists() else []
    if not cand:
        workdir = BASE / task["workdir"]
        old = workdir / ("claude_result.json" if task["agent"] == "claude" else "hermes_result.txt")
        if old.exists():
            cand = [old]
    return cand


def review_workdir(workdir):
    wd = Path(workdir)
    if not wd.is_dir():
        return [], [f"工作目录不存在: {wd}"]
    files = sorted(p.name for p in wd.iterdir() if p.is_file())
    py_files = [p for p in Path(workdir).iterdir() if p.suffix == ".py"]
    issues = []
    for p in py_files:
        try:
            r = subprocess.run([sys.executable, "-m", "py_compile", str(p)],
                               capture_output=True, timeout=60)
            if r.returncode != 0:
                issues.append(p.name)
        except subprocess.TimeoutExpired:
            issues.append(p.name + " (语法检查超时)")
        except FileNotFoundError:
            issues.append(p.name + " (Python 解释器不可用)")
    return files, issues


def cmd_report(tasks):
    print("=" * 66)
    print("多 Agent 编排报告（基于已有结果，免费模式）")
    print("=" * 66)
    for t in tasks:
        print("\n[{name}] agent={agent} workdir={workdir}".format(**t))
        cand = find_results(t)
        if not cand:
            # 无主结果文件时，检查是否存在失败标记（超时/命令不可用）
            shown = False
            for suffix in (".timeout.txt", ".error.txt"):
                ef = RESULTS / (t["name"] + suffix)
                if ef.exists():
                    print("  失败标记: " + ef.read_text(encoding="utf-8").strip())
                    shown = True
            if not shown:
                print("  无结果文件（尚未执行）")
        for c in cand:
            if t["agent"] == "claude" and c.suffix == ".json":
                info = analyze_claude(c)
                print("  Claude Code: ok={ok} 耗时={dur}ms 成本=${cost} 摘要={summ!r}".format(
                    ok=info.get("ok"), dur=info.get("duration_ms"),
                    cost=info.get("cost_usd"), summ=info.get("result", "")))
            elif t["agent"] == "hermes" and c.suffix == ".txt":
                info = analyze_hermes(c)
                print("  Hermes: ok={ok} {session}".format(**info))
        files, issues = review_workdir(BASE / t["workdir"])
        print("  产物: " + (", ".join(files) if files else "(无)"))
        if issues:
            print("  警告: 语法检查失败 -> " + ", ".join(issues))
        else:
            print("  语法检查: 通过")


def cmd_run(tasks):
    if not tasks:
        print("警告：没有匹配的任务（tasks.json 中无任务或 --only 过滤掉了全部任务）")
        return
    print("派发 {} 个子任务（真实调用 Agent，会产生费用）...".format(len(tasks)))
    for t in tasks:
        print("\n>> [{name}] -> {agent} @ {workdir}".format(**t))
        r = run_agent(t)
        print("   完成: ok={ok} 耗时={elapsed_sec}s 输出={output}".format(**r))
        files, issues = review_workdir(BASE / t["workdir"])
        print("   产物: " + (", ".join(files) if files else "(无)"))
        if issues:
            print("   警告: 语法检查失败 -> " + ", ".join(issues))


def cmd_noop(tasks):
    if not tasks:
        print("警告：没有匹配的任务（tasks.json 中无任务或 --only 过滤掉了全部任务）")
        return
    for t in tasks:
        prompt = DEFAULT_PROMPT.format(prompt=t.get("prompt_file", "TASK.md"))
        cmd = build_command(t, prompt)
        out = result_path(t)
        print("{name:20s} -> {cmd}  (输出: {out})".format(
            name=t["name"], cmd=" ".join(cmd), out=out))


def main():
    ap = argparse.ArgumentParser(description="多 Agent 编排工具")
    ap.add_argument("--report", action="store_true", help="分析已有结果（免费）")
    ap.add_argument("--list", action="store_true", help="列出任务配置")
    ap.add_argument("--noop", action="store_true", help="只打印命令不执行（免费）")
    ap.add_argument("--only", default=None, help="只处理指定任务名（逗号分隔）")
    args = ap.parse_args()

    tasks = load_tasks()
    if args.only:
        names = [n.strip() for n in args.only.split(",")]
        tasks = [t for t in tasks if t["name"] in names]
    if args.list:
        for t in tasks:
            print("{name:20s} agent={agent:6s} workdir={workdir}".format(**t))
    elif args.report:
        if not tasks:
            print("警告：没有匹配的任务（tasks.json 中无任务或 --only 过滤掉了全部任务）")
        else:
            cmd_report(tasks)
    elif args.noop:
        cmd_noop(tasks)
    else:
        cmd_run(tasks)


if __name__ == "__main__":
    main()
