# coding: utf-8
"""来源无关的数据缓存读写(任务卡_卡1 第一节第2条)。

布局:
    cache/{table}/_parts/{source}__{chunk}.parquet   # 分片:一次拉取的原子产物,存在即"已完成"(断点续传依据)
    cache/{table}/{table}.parquet                    # 合并表:分片按来源优先级去重、按主键排序,带 source 溯源列
写入走"临时文件→原子替换",校验失败不留残片。
路径来自 config meta.cache_dir(相对仓库根),测试可传 root 覆盖。
"""
import glob
import os

import pandas as pd
import pyarrow.parquet as pq

from core.config import ROOT, get
from data.schema import get_spec, validate

PARTS_DIR = "_parts"


# ---------- 路径 ----------

def cache_root(cfg=None, root=None):
    root = root or ROOT
    rel = get(cfg or {}, "meta.cache_dir", "cache")
    return rel if os.path.isabs(rel) else os.path.join(root, rel)


def table_dir(name, cfg=None, root=None):
    return os.path.join(cache_root(cfg, root), name)


def table_path(name, cfg=None, root=None):
    return os.path.join(table_dir(name, cfg, root), name + ".parquet")


def _safe_chunk(chunk):
    return str(chunk).replace("/", "_").replace("\\", "_").replace(":", "-")


def part_path(name, source, chunk, cfg=None, root=None):
    return os.path.join(table_dir(name, cfg, root), PARTS_DIR, "%s__%s.parquet" % (source, _safe_chunk(chunk)))


def _atomic_write(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


# ---------- 分片 ----------

def has_part(name, source, chunk, cfg=None, root=None):
    return os.path.exists(part_path(name, source, chunk, cfg, root))


def write_part(name, source, chunk, df, cfg=None, root=None):
    """校验后写分片(空DataFrame也写:代表"该分片已拉过、确实无数据")。返回路径。"""
    spec = get_spec(name)
    df = df.copy()
    if "source" not in df.columns:
        df["source"] = source
    validated = validate(df, spec)
    path = part_path(name, source, chunk, cfg, root)
    _atomic_write(validated, path)
    return path


def list_parts(name, cfg=None, root=None):
    """返回 [(source, chunk, path)],按文件名排序。"""
    pattern = os.path.join(table_dir(name, cfg, root), PARTS_DIR, "*.parquet")
    out = []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)[:-len(".parquet")]
        source, _, chunk = base.partition("__")
        out.append((source, chunk, path))
    return out


# ---------- 合并与读取 ----------

def _empty_frame(spec):
    return pd.DataFrame({c: pd.Series(dtype=object) for c in list(spec.columns) + ["source"]})


def consolidate(name, source_priority=None, cfg=None, root=None):
    """合并全部分片 → cache/{table}/{table}.parquet。主键冲突时按来源优先级保留
    (优先级列表外的来源排最后)。返回合并后的 DataFrame。"""
    spec = get_spec(name)
    priority = list(source_priority or get(cfg or {}, "data.source_priority", []))
    frames = [pd.read_parquet(p) for _, _, p in list_parts(name, cfg, root)]
    frames = [f for f in frames if len(f)]
    if not frames:
        df = _empty_frame(spec)
    else:
        df = pd.concat(frames, ignore_index=True)
        rank = df["source"].map(lambda s: priority.index(s) if s in priority else len(priority))
        df = df.assign(_rank=rank).sort_values("_rank", kind="stable")
        df = df.drop_duplicates(subset=list(spec.key), keep="first").drop(columns="_rank")
        df = validate(df, spec)
    _atomic_write(df, table_path(name, cfg, root))
    return df


def _pushdown_filters(spec, start, end, symbols):
    """把区间/标的条件下推到 parquet 读取(pyarrow 在 C++ 层过滤,不整表进 pandas)。
    只对 spec 里真有的列生成条件;下推后 pandas 侧再过一遍作为语义兜底。"""
    filters = []
    if spec.date_col:
        if start is not None:
            filters.append((spec.date_col, ">=", pd.Timestamp(start)))
        if end is not None:
            filters.append((spec.date_col, "<=", pd.Timestamp(end)))
    if symbols is not None and "symbol" in spec.columns:
        filters.append(("symbol", "in", list(symbols)))
    return filters or None


def read_table(name, start=None, end=None, symbols=None, columns=None, cfg=None, root=None):
    """读合并表并按日期区间/标的/列裁剪;表不存在返回带 spec 列的空表(不返回 None)。"""
    spec = get_spec(name)
    path = table_path(name, cfg, root)
    if not os.path.exists(path):
        df = _empty_frame(spec)
    else:
        df = pd.read_parquet(path, filters=_pushdown_filters(spec, start, end, symbols))
    if spec.date_col and len(df):
        if start is not None:
            df = df[df[spec.date_col] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df[spec.date_col] <= pd.Timestamp(end)]
    if symbols is not None and "symbol" in df.columns:
        df = df[df["symbol"].isin(list(symbols))]
    if columns is not None:
        df = df[list(columns)]
    return df.reset_index(drop=True)


def date_range(name, cfg=None, root=None):
    """合并表日期列的 (min, max),只读 parquet 行组统计不读数据;表不存在或无日期列返回 (None, None)。"""
    spec = get_spec(name)
    path = table_path(name, cfg, root)
    if not spec.date_col or not os.path.exists(path):
        return None, None
    meta = pq.ParquetFile(path).metadata
    col_idx = meta.schema.names.index(spec.date_col)
    lo, hi = None, None
    for i in range(meta.num_row_groups):
        st = meta.row_group(i).column(col_idx).statistics
        if st is None or not st.has_min_max:
            continue
        lo = st.min if lo is None else min(lo, st.min)
        hi = st.max if hi is None else max(hi, st.max)
    if lo is None:
        return None, None
    return pd.Timestamp(lo), pd.Timestamp(hi)


def table_status(name, cfg=None, root=None):
    spec = get_spec(name)
    path = table_path(name, cfg, root)
    status = {"table": name, "exists": os.path.exists(path), "rows": 0, "parts": len(list_parts(name, cfg, root)),
              "date_min": None, "date_max": None, "sources": {}}
    if not status["exists"]:
        return status
    df = pd.read_parquet(path)
    status["rows"] = int(len(df))
    if spec.date_col and len(df):
        status["date_min"] = df[spec.date_col].min().date().isoformat()
        status["date_max"] = df[spec.date_col].max().date().isoformat()
    if "source" in df.columns and len(df):
        status["sources"] = {k: int(v) for k, v in df["source"].value_counts().items()}
    return status
