# coding: utf-8
"""示踪弹(卡7):用同一个玩具策略按 SOP 顺序跑通 S0→S1→S2→S3/S4→S5→面板,出一份可追溯的示踪报告。

每环节 = 一条子进程命令(各卡既有入口,不重复实现)或一个 python 检查;失败不中断、标红继续;
报告 reports/{date}_示踪弹/trace.md(环节表 + 产出路径 + 总判定)。跑通 = 框架 v1 完工判据(蓝图第八节)。
用法:python -m tools.tracer [--date 2026-08-28] [--skip S2,S3/S4]
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from core.config import ROOT
from core.outputs import report_dir

STRATEGY = "toy_lowvol"


@dataclass
class Stage:
    name: str
    title: str
    cmd: list = None                 # 子进程命令
    check: object = None             # 或 python 检查:() -> (passed, message)
    accept: object = None            # 可选:(exit_code, output) -> (passed, note),覆盖"退出码=0 即通过"
    outputs: list = field(default_factory=list)   # 产出相对路径(报告用)


# ---------- 各环节的判据(来自各卡,示踪弹只引用不重定义) ----------

def check_ideas():
    path = os.path.join(ROOT, "research", "ideas.md")
    with open(path, encoding="utf-8") as f:
        rows = [l for l in f if l.startswith("|") and STRATEGY in l]
    if not rows:
        return False, "research/ideas.md 没有 %s 的登记行(S0 未做)" % STRATEGY
    if any("废弃" in r.split("|")[6] for r in rows if len(r.split("|")) > 6):
        return False, "登记行状态为废弃"
    return True, "ideas.md 已登记:%s" % rows[-1].strip()[:80]


def accept_quality(date):
    """S1:退出 0 通过;退出 2 时若只有覆盖率项未通过 → 按卡1 人类核验(2015 股灾停牌假阳性,数据已接受)通过。"""
    def _accept(code, output):
        if code == 0:
            return True, "四项全部通过"
        path = os.path.join(ROOT, "reports", "%s_数据体检" % date, "quality_report.md")
        if not os.path.exists(path):
            return False, "退出码 %d 且找不到体检报告" % code
        with open(path, encoding="utf-8") as f:
            text = f.read()
        failed = [l for l in text.splitlines() if l.startswith("## ") and "未通过" in l]
        if failed and all("覆盖" in l for l in failed):
            return True, "仅覆盖率项未通过(卡1 人类核验:2015 股灾千股停牌假阳性,数据已接受)"
        return False, "未通过项:%s" % "; ".join(failed) or "未知"
    return _accept


def accept_signal(code, output):
    """S5:出信号成功通过;数据不新鲜而拒绝也是正确行为(军规9),记通过并注明。"""
    if code == 0:
        return True, "信号文件已生成"
    if "数据不新鲜" in output:
        return True, "数据不新鲜,正确拒绝出信号(军规9)"
    return False, "退出码 %d" % code


def check_dashboard():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "dashboard", "app.py"), default_timeout=300).run()
    if at.exception:
        return False, "面板首屏异常:%s" % at.exception
    for screen in at.sidebar.radio[0].options:
        at = at.sidebar.radio[0].set_value(screen).run()
        if at.exception:
            return False, "屏「%s」异常:%s" % (screen, at.exception)
    return True, "AppTest 四屏无异常(只读)"


def build_stages(date, python=None, skip=()):
    py = python or sys.executable
    stages = [
        Stage("S0", "想法登记", check=check_ideas, outputs=["research/ideas.md"]),
        Stage("S1", "数据体检", cmd=[py, "-m", "data.quality", "--date", date], accept=accept_quality(date),
              outputs=["reports/%s_数据体检/quality_report.md" % date]),
        Stage("S2", "因子检验(对照组 + 裁决)", cmd=[py, "-m", "factors.run_factor_tests", "--date", date],
              outputs=["reports/%s_卡4因子检验/factor_verdict.md" % date, "factors/registry.yaml"]),
        Stage("S3/S4", "回测 + 交叉验证", cmd=[py, "-m", "backtest.run_rqalpha_toy", "--date", date],
              outputs=["reports/%s_卡3阶段C/toy_lowvol_cross_validation.md" % date]),
        Stage("S5", "信号", cmd=[py, "-m", "signals.run_signal", "--strategy", STRATEGY], accept=accept_signal,
              outputs=["reports/%s_信号_%s/" % (date, STRATEGY)]),
        Stage("面板", "面板无头冒烟", check=check_dashboard, outputs=["dashboard/app.py"]),
    ]
    return [s for s in stages if s.name not in set(skip)]


# ---------- 纯编排 ----------

def subprocess_runner(stage):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(stage.cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out


def run_stages(stages, runner=None):
    """逐环节执行,失败不中断。runner(stage) -> (exit_code, output);check 型环节不经 runner。"""
    runner = runner or subprocess_runner
    records = []
    for st in stages:
        t0 = time.time()
        if st.check is not None:
            try:
                passed, note = st.check()
            except Exception as e:      # 环节内部错误也要记录,不中断示踪
                passed, note = False, "检查异常:%r" % (e,)
            code, output = (0 if passed else 1), note
        else:
            code, output = runner(st)
            if st.accept is not None:
                passed, note = st.accept(code, output)
                output = note + "\n" + output
            else:
                passed = code == 0
        records.append({"name": st.name, "title": st.title, "cmd": " ".join(st.cmd) if st.cmd else "", "exit_code": code,
                        "passed": bool(passed), "seconds": time.time() - t0, "output": output, "outputs": list(st.outputs)})
    return records


def _tail(text, n=12):
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def write_trace(out_dir, records, date):
    os.makedirs(out_dir, exist_ok=True)
    ok = all(r["passed"] for r in records)
    lines = ["# 示踪弹报告(%s)· 玩具策略 %s 全流程" % (date, STRATEGY), "",
             "总判定:**%s**(%d/%d 环节通过,合计 %.0f 秒)" % ("全部通过 → 框架 v1 完工判据达成" if ok else "不通过",
                                                          sum(r["passed"] for r in records), len(records),
                                                          sum(r["seconds"] for r in records)), "",
             "| 环节 | 内容 | 结果 | 耗时 | 产出 |", "|---|---|---|---|---|"]
    for r in records:
        lines.append("| %s | %s | %s | %.0fs | %s |" % (r["name"], r["title"], "通过" if r["passed"] else "**不通过**",
                                                       r["seconds"], "<br>".join("`%s`" % o for o in r.get("outputs", []))))
    lines += ["", "## 各环节末尾输出", ""]
    for r in records:
        lines += ["### %s %s(退出码 %s)" % (r["name"], r["title"], r.get("exit_code", "")), "",
                  "`%s`" % r["cmd"] if r.get("cmd") else "(python 检查)", "", "```", _tail(r.get("output", "")), "```", ""]
    path = os.path.join(out_dir, "trace.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--skip", default="", help="逗号分隔要跳过的环节名,如 S2,S3/S4")
    args = ap.parse_args()
    log = init("tracer")
    skip = {x.strip() for x in args.skip.split(",") if x.strip()}
    stages = build_stages(args.date, skip=skip)
    records = []
    for st in stages:
        log.info("▶ %s %s", st.name, st.title)
        rec = run_stages([st])[0]
        records.append(rec)
        log.info("%s %s:%s(%.0fs)%s", "✅" if rec["passed"] else "❌", st.name, "通过" if rec["passed"] else "不通过",
                 rec["seconds"], "" if rec["passed"] else "\n" + _tail(rec["output"], 6))
    path = write_trace(report_dir("示踪弹", date=args.date), records, args.date)
    print("示踪报告:", path)
    return 0 if all(r["passed"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
