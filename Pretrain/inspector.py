"""
inspector.py - Lõi xử lý (CỐ ĐỊNH, không cần sửa theo từng dataset).

Chức năng:
  1. Dùng PyOD (ECOD) chấm điểm bất thường trên các cột số.
  2. Xuất ảnh tĩnh data_health_report.png (chấm đỏ = lỗi, chấm xanh = sạch).
  3. Xuất data_clean.csv và data_report.csv.
  4. Mở Renumics Spotlight (offline, localhost) để duyệt tương tác.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")  # Backend không cần màn hình -> an toàn khi chạy CLI/server
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402

log = logging.getLogger("inspector")

# Tên các cột do inspector thêm vào
COL_SCORE = "outlier_score"
COL_FLAG = "is_outlier"
COL_STATUS = "status"
STATUS_BAD = "LỖI / OUTLIER"
STATUS_OK = "SẠCH"
HELPER_COLS = [COL_SCORE, COL_FLAG, COL_STATUS, "map_x", "map_y"]

AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

COLOR_OK = "#1f77b4"   # xanh
COLOR_BAD = "#e41a1c"  # đỏ


class UniversalDataInspector:
    """Phát hiện outlier, xuất báo cáo và mở Spotlight cho một DataFrame bất kỳ."""

    def __init__(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        output_root: str | os.PathLike = "outputs",
        contamination: float = 0.05,
        image_col: Optional[str] = None,
        text_col: Optional[str] = None,
        audio_col: Optional[str] = None,
    ) -> None:
        if df is None or df.empty:
            raise ValueError("DataFrame rỗng - không có gì để kiểm tra.")
        if not 0 < contamination < 0.5:
            raise ValueError("contamination phải nằm trong khoảng (0, 0.5).")

        self.df = df.reset_index(drop=True).copy()
        self.dataset_name = dataset_name
        self.contamination = contamination
        self.image_col = self._check_col(image_col, "image_col")
        self.text_col = self._check_col(text_col, "text_col")
        self.audio_col = self._check_col(audio_col, "audio_col")

        self.out_dir = Path(output_root) / dataset_name
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.numeric_cols: List[str] = []
        self.report: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------ #
    # Tiện ích
    # ------------------------------------------------------------------ #
    def _check_col(self, col: Optional[str], label: str) -> Optional[str]:
        """Kiểm tra cột người dùng chỉ định có tồn tại không."""
        if col and col not in self.df.columns:
            log.warning("%s='%s' không có trong dữ liệu -> bỏ qua.", label, col)
            return None
        return col

    def _select_numeric(self) -> pd.DataFrame:
        """Lấy các cột số hữu ích: bỏ cột hằng, cột toàn NaN; điền NaN bằng median."""
        num = self.df.select_dtypes(include=[np.number]).copy()
        num = num.replace([np.inf, -np.inf], np.nan)
        num = num.dropna(axis=1, how="all")
        num = num.loc[:, num.nunique(dropna=True) > 1]
        if num.shape[1] == 0:
            raise ValueError(
                "Không có cột số nào dùng được để phát hiện outlier. "
                "Hãy chuyển kiểu dữ liệu trong preprocess.py."
            )
        self.numeric_cols = list(num.columns)
        return num.fillna(num.median())

    # ------------------------------------------------------------------ #
    # 1. Phát hiện outlier
    # ------------------------------------------------------------------ #
    def detect(self) -> pd.DataFrame:
        """Chạy ECOD, gắn outlier_score / is_outlier / status và tọa độ 2D."""
        from pyod.models.ecod import ECOD

        X = self._select_numeric()
        log.info("ECOD trên %d mẫu x %d cột số.", *X.shape)

        model = ECOD(contamination=self.contamination)
        model.fit(X.values)

        df = self.df
        df[COL_SCORE] = model.decision_scores_.astype(float)
        df[COL_FLAG] = model.labels_.astype(int).astype(bool)
        df[COL_STATUS] = np.where(df[COL_FLAG], STATUS_BAD, STATUS_OK)

        df["map_x"], df["map_y"] = self._project_2d(X.values)
        self.report = df
        log.info("Phát hiện %d outlier / %d mẫu.", int(df[COL_FLAG].sum()), len(df))
        return df

    @staticmethod
    def _project_2d(X: np.ndarray):
        """Chiếu dữ liệu xuống 2D bằng PCA (chuẩn hóa trước)."""
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        Xs = StandardScaler().fit_transform(X)
        if Xs.shape[1] == 1:  # chỉ 1 cột số -> trục y = chỉ số dòng
            return Xs[:, 0], np.arange(len(Xs), dtype=float)
        coords = PCA(n_components=2, random_state=0).fit_transform(Xs)
        return coords[:, 0], coords[:, 1]

    # ------------------------------------------------------------------ #
    # 2 & 3. Xuất file
    # ------------------------------------------------------------------ #
    def save_reports(self) -> Dict[str, Path]:
        """Lưu data_report.csv, data_clean.csv và data_health_report.png."""
        if self.report is None:
            self.detect()
        df = self.report
        paths = {
            "report": self.out_dir / "data_report.csv",
            "clean": self.out_dir / "data_clean.csv",
            "plot": self.out_dir / "data_health_report.png",
        }

        # utf-8-sig để Excel đọc đúng tiếng Việt
        df.drop(columns=["map_x", "map_y"]).to_csv(
            paths["report"], index=False, encoding="utf-8-sig"
        )
        clean = df.loc[~df[COL_FLAG]].drop(columns=HELPER_COLS)
        clean.to_csv(paths["clean"], index=False, encoding="utf-8-sig")

        self._plot(paths["plot"])
        for k, p in paths.items():
            log.info("Đã lưu %-6s -> %s", k, p)
        return paths

    def _plot(self, path: Path) -> None:
        """Vẽ ảnh tĩnh: histogram điểm bất thường + scatter chấm đỏ/xanh."""
        df = self.report
        ok, bad = df[~df[COL_FLAG]], df[df[COL_FLAG]]
        sns.set_theme(style="whitegrid")
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))

        # Subplot 1: phân bố anomaly score
        sns.histplot(df[COL_SCORE], bins=50, color="#7f7f7f", ax=axes[0])
        if len(bad):
            thr = bad[COL_SCORE].min()
            axes[0].axvline(thr, color=COLOR_BAD, ls="--", label=f"Ngưỡng lỗi ≈ {thr:.2f}")
            axes[0].legend()
        axes[0].set_title("Phân bố Anomaly Score (ECOD)")
        axes[0].set_xlabel("outlier_score")
        axes[0].set_ylabel("Số mẫu")

        # Subplot 2: scatter 2D, sạch = xanh, lỗi = đỏ nổi bật
        axes[1].scatter(ok["map_x"], ok["map_y"], s=18, c=COLOR_OK, alpha=0.6,
                        label=f"{STATUS_OK} ({len(ok)})")
        axes[1].scatter(bad["map_x"], bad["map_y"], s=60, c=COLOR_BAD, alpha=0.95,
                        edgecolors="black", linewidths=0.6, zorder=3,
                        label=f"{STATUS_BAD} ({len(bad)})")
        axes[1].set_title("Bản đồ dữ liệu 2D (PCA) - chấm đỏ là dữ liệu lỗi")
        axes[1].set_xlabel("Thành phần 1")
        axes[1].set_ylabel("Thành phần 2")
        axes[1].legend()

        fig.suptitle(f"Data Health Report - {self.dataset_name}", fontsize=15)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)

    # ------------------------------------------------------------------ #
    # 4. Renumics Spotlight
    # ------------------------------------------------------------------ #
    def _guess_media_cols(self) -> Dict[str, str]:
        """Tự nhận diện cột ảnh / audio theo đuôi file nếu người dùng không chỉ định."""
        found: Dict[str, str] = {}
        for col in self.df.select_dtypes(include=["object", "string"]).columns:
            sample = self.df[col].dropna().astype(str).head(20).str.lower()
            if sample.empty:
                continue
            if sample.str.endswith(IMAGE_EXT).all():
                found[col] = "image"
            elif sample.str.endswith(AUDIO_EXT).all():
                found[col] = "audio"
        return found

    def launch_spotlight(self, port: Optional[int] = None, host: str = "127.0.0.1") -> None:
        """Mở Spotlight local. Trong UI: Color by -> 'status' để thấy đỏ/xanh."""
        try:
            from renumics import spotlight
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Chưa cài renumics-spotlight. Chạy: pip install renumics-spotlight"
            ) from e

        if self.report is None:
            self.detect()

        view = self.report.copy()
        dtype: Dict[str, type] = {}

        # Cột media: ưu tiên tham số người dùng, sau đó tự nhận diện
        guessed = self._guess_media_cols()
        if self.image_col:
            guessed[self.image_col] = "image"
        if self.audio_col:
            guessed[self.audio_col] = "audio"
        for col, kind in guessed.items():
            dtype[col] = spotlight.Image if kind == "image" else spotlight.Audio
            # Spotlight cần đường dẫn tuyệt đối để đọc file local
            view[col] = view[col].map(
                lambda v: str(Path(v).resolve()) if isinstance(v, str) and Path(v).exists() else v
            )
        if self.text_col:
            dtype[self.text_col] = str  # hiển thị dạng text (full)

        dtype[COL_FLAG] = bool

        log.info("Mở Spotlight tại http://%s:%s (Ctrl+C để dừng)", host, port or "auto")
        spotlight.show(
            view,
            dtype=dtype or None,
            host=host,
            port=port if port else "auto",
            wait="forever",   # giữ tiến trình sống cho tới khi Ctrl+C
            no_browser=False,
        )

    # ------------------------------------------------------------------ #
    # Chạy toàn bộ
    # ------------------------------------------------------------------ #
    def run(self, launch_ui: bool = True, port: Optional[int] = None) -> Dict[str, Path]:
        self.detect()
        paths = self.save_reports()
        if launch_ui:
            self.launch_spotlight(port=port)
        return paths
