# coding: utf-8
"""pre-commit密钥扫描(自cb_quant平移,规则原样):防止token/cookie类敏感值进git。

背景(旧项目实战教训):config.snapshot.yaml(含tushare token)曾在报告文件夹被
gitignore重新纳入后差点入库,人工拦截不可靠,改成pre-commit硬闸。

检查两层:
1. 禁止文件名:config.yaml / config.snapshot.yaml(无论在哪个目录)——这两类文件
   永远不该被staged(约定:参数经git的唯一途径是 config.example.yaml 的结构快照)。
2. 内容扫描:staged内容里出现≥41位连续hex即拦截(tushare token 60位hex属此类;
   40位整放行——git commit id 常见于文档引用)。

用法:
    python tools/check_secrets.py                 # 扫描当前staged内容,发现问题exit 1
    python tools/check_secrets.py --scan-dir 路径  # 全量扫描目录(交付/导出前用)
安装为pre-commit钩子(每个clone装一次,.git/hooks不进git):
    printf '#!/bin/sh\\nexec .venv/Scripts/python.exe tools/check_secrets.py\\n' > .git/hooks/pre-commit
"""
import re
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FORBIDDEN_BASENAMES = {"config.yaml", "config.snapshot.yaml"}
# >40位连续hex(40位放行:git commit id;41+位拦截:tushare token 60位hex属此类)
LONG_HEX = re.compile(r"\b[0-9a-fA-F]{41,}\b")


def forbidden_filename(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1] in FORBIDDEN_BASENAMES


def scan_content(text):
    """返回命中的可疑串列表(截断显示前12位,避免报错信息本身泄露完整值)。"""
    return ["%s...(共%d位hex)" % (m[:12], len(m)) for m in LONG_HEX.findall(text)]


def staged_files():
    # ⚠ 必须用-z(NUL分隔原始字节路径):默认输出会把中文文件名转成带引号的八进制
    # 转义形式,直接喂给git show会404(旧项目在中文文件名的预注册文档上踩过)
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"],
                          capture_output=True, check=True)
    return [p.decode("utf-8") for p in out.stdout.split(b"\0") if p.strip()]


def staged_content(path):
    out = subprocess.run(["git", "show", ":%s" % path], capture_output=True, check=True)
    try:
        return out.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None   # 二进制文件(png/parquet等)不做内容扫描


def scan_directory(root):
    """全量扫描目录(导出/交付前用):禁止文件名+内容长hex,返回错误列表。
    二进制文件(utf-8解码失败)跳过内容扫描但仍查文件名。"""
    import os
    errors = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if forbidden_filename(fn):
                errors.append("禁止的文件名: %s(config类文件不进交付包)" % rel)
                continue
            try:
                with open(full, encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for hit in scan_content(text):
                errors.append("%s: 疑似密钥 %s" % (rel, hit))
    return errors


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", default=None, help="全量扫描指定目录而不是git staged内容")
    args = ap.parse_args(argv)

    if args.scan_dir:
        errors = scan_directory(args.scan_dir)
        label = "目录 %s 扫描" % args.scan_dir
    else:
        errors = []
        for path in staged_files():
            if forbidden_filename(path):
                errors.append("禁止staged的文件名: %s(config类文件不进git)" % path)
                continue
            text = staged_content(path)
            if text is None:
                continue
            for hit in scan_content(text):
                errors.append("%s: 疑似密钥 %s" % (path, hit))
        label = "本次提交"

    if errors:
        print("[check_secrets] 拦截%s:" % label)
        for e in errors:
            print("  -", e)
        print("确认误报的话,修掉可疑串或调整tools/check_secrets.py的规则后重试;不要--no-verify绕过。")
        return 1
    print("[check_secrets] %s: 零命中" % label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
