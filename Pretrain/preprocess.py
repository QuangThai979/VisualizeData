"""
preprocess.py - SỬA FILE NÀY cho từng dataset.

Hàm preprocess_data(df, base_dir) nhận DataFrame thô và trả về DataFrame
sẵn sàng đưa vào inspector.py. Mặc định đã làm các bước chung; bổ sung
logic riêng của dataset vào khu vực "TÙY BIẾN" bên dưới.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("preprocess")


def _clean_name(name: str) -> str:
    """Chuẩn hóa tên cột: bỏ dấu, chữ thường, ký tự lạ -> '_'."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s or "col"


def _dedupe(names):
    """Đảm bảo tên cột không trùng nhau."""
    seen, out = {}, []
    for n in names:
        seen[n] = seen.get(n, -1) + 1
        out.append(n if seen[n] == 0 else f"{n}_{seen[n]}")
    return out


def preprocess_data(df: pd.DataFrame, base_dir: Optional[Path] = None) -> pd.DataFrame:
    """Tiền xử lý chung. `base_dir` là thư mục để giải đường dẫn file ảnh/audio tương đối."""
    df = df.copy()

    # --- 1. Làm sạch tên cột ---
    df.columns = _dedupe([_clean_name(c) for c in df.columns])

    # --- 2. Bỏ dòng/cột rỗng hoàn toàn & dòng trùng lặp ---
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    n_before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    if len(df) < n_before:
        log.info("Đã bỏ %d dòng trùng lặp.", n_before - len(df))

    # --- 3. Ép kiểu cơ bản ---
    for col in df.columns:
        if df[col].dtype == object:
            s = df[col].astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "None": np.nan})
            # Thử chuyển sang số nếu >= 90% giá trị parse được
            as_num = pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")
            if s.notna().sum() and as_num.notna().sum() / s.notna().sum() >= 0.9:
                df[col] = as_num
                continue
            # Thử chuyển sang thời gian (chỉ khi tên cột gợi ý) rồi đổi thành timestamp số
            if re.search(r"date|time|ngay|thoi_gian|timestamp", col):
                dt = pd.to_datetime(s, errors="coerce")
                if dt.notna().mean() >= 0.9:
                    df[col] = dt
                    continue
            df[col] = s

    # Cột datetime -> số (giây epoch) để ECOD dùng được, giữ cột gốc dạng chuỗi
    for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df[f"{col}_ts"] = df[col].astype("int64", errors="ignore") // 10**9
        df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    # --- 4. Giải đường dẫn file ảnh/audio local thành đường dẫn tuyệt đối ---
    if base_dir is not None:
        media_ext = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
                     ".wav", ".mp3", ".flac", ".ogg", ".m4a")
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().astype(str).head(20).str.lower()
            if len(sample) and sample.str.endswith(media_ext).all():
                df[col] = df[col].map(
                    lambda v: str((Path(base_dir) / v).resolve())
                    if isinstance(v, str) and not Path(v).is_absolute() and (Path(base_dir) / v).exists()
                    else v
                )

    # ===================== TÙY BIẾN THEO DATASET =====================
    # Ví dụ:
    #   df = df[df["price"] > 0]                      # loại giá trị vô lý
    #   df["area_log"] = np.log1p(df["area"])         # biến đổi log
    #   df = df.drop(columns=["id"])                  # bỏ cột định danh
    # =================================================================

    return df
