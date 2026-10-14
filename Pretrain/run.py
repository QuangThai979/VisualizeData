"""
run.py - Điểm chạy chính (CLI).

Ví dụ:
    python run.py data/input/houses.csv
    python run.py data/input/products.csv --image_col image_path --text_col description --port 8080
    python run.py data/input/my_images_folder          # thư mục ảnh/audio
"""
from __future__ import annotations

import argparse
import logging
import sys
import wave
from pathlib import Path

import pandas as pd

from inspector import UniversalDataInspector, IMAGE_EXT, AUDIO_EXT
from preprocess import preprocess_data

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "outputs"

log = logging.getLogger("run")


def _media_folder_to_df(folder: Path) -> pd.DataFrame:
    """Quét thư mục ảnh/audio và trích đặc trưng số đơn giản để chấm outlier."""
    rows = []
    for p in sorted(folder.rglob("*")):
        ext = p.suffix.lower()
        if ext in IMAGE_EXT:
            try:
                from PIL import Image
                import numpy as np
                with Image.open(p) as im:
                    arr = np.asarray(im.convert("L"), dtype=float)
                    rows.append({"image_path": str(p), "width": im.width, "height": im.height,
                                 "file_size": p.stat().st_size,
                                 "brightness": arr.mean(), "contrast": arr.std()})
            except Exception as e:  # file ảnh hỏng cũng là một dạng lỗi dữ liệu
                log.warning("Không đọc được ảnh %s: %s", p, e)
                rows.append({"image_path": str(p), "width": 0, "height": 0,
                             "file_size": p.stat().st_size, "brightness": 0.0, "contrast": 0.0})
        elif ext in AUDIO_EXT:
            dur = 0.0
            if ext == ".wav":
                try:
                    with wave.open(str(p)) as w:
                        dur = w.getnframes() / float(w.getframerate())
                except Exception as e:
                    log.warning("Không đọc được audio %s: %s", p, e)
            rows.append({"audio_path": str(p), "file_size": p.stat().st_size, "duration_sec": dur})
    if not rows:
        raise ValueError(f"Không tìm thấy ảnh/audio trong thư mục: {folder}")
    return pd.DataFrame(rows)


def load_input(path: Path) -> pd.DataFrame:
    """Đọc dữ liệu theo định dạng: csv/tsv/parquet/xlsx/json, thư mục media, hoặc 1 file ảnh/audio."""
    if path.is_dir():
        return _media_folder_to_df(path)
    ext = path.suffix.lower()
    if ext in (".csv", ".txt"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(path, sep=None, engine="python", encoding="latin-1")
    if ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext in (".json", ".jsonl"):
        return pd.read_json(path, lines=(ext == ".jsonl"))
    if ext in IMAGE_EXT + AUDIO_EXT:
        raise ValueError("Một file media đơn lẻ không đủ để so sánh outlier; hãy trỏ tới thư mục chứa nhiều file.")
    raise ValueError(f"Định dạng '{ext}' chưa được hỗ trợ.")


def resolve_input(arg: str) -> Path:
    """Chấp nhận đường dẫn trực tiếp hoặc tên file nằm trong data/input."""
    for cand in (Path(arg), INPUT_DIR / arg, ROOT / arg):
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError(f"Không tìm thấy dữ liệu: {arg} (đã tìm trong {INPUT_DIR})")


def main() -> int:
    # Console Windows mặc định không phải UTF-8 -> ép UTF-8 để in tiếng Việt
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Universal Data Inspector (PyOD ECOD + Renumics Spotlight)")
    ap.add_argument("input", help="Đường dẫn file/thư mục dữ liệu, ví dụ data/input/abc.csv")
    ap.add_argument("--image_col", help="Tên cột chứa đường dẫn ảnh")
    ap.add_argument("--text_col", help="Tên cột chứa văn bản")
    ap.add_argument("--audio_col", help="Tên cột chứa đường dẫn audio")
    ap.add_argument("--port", type=int, default=None, help="Cổng Spotlight (mặc định: tự chọn)")
    ap.add_argument("--contamination", type=float, default=0.05, help="Tỉ lệ outlier kỳ vọng (0-0.5), mặc định 0.05")
    ap.add_argument("--no_ui", action="store_true", help="Chỉ xuất báo cáo, không mở Spotlight")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    try:
        in_path = resolve_input(args.input)
        dataset_name = in_path.stem if in_path.is_file() else in_path.name  # <tên_dataset>
        log.info("Dataset: %s (%s)", dataset_name, in_path)

        # 1. Đọc dữ liệu
        raw = load_input(in_path)
        log.info("Đọc được %d dòng x %d cột.", *raw.shape)

        # 2-3. Tiền xử lý (tên cột bị chuẩn hóa -> chuẩn hóa tên cột người dùng truyền vào cho khớp)
        from preprocess import _clean_name
        df = preprocess_data(raw, base_dir=in_path.parent if in_path.is_file() else in_path)
        cols = {k: (_clean_name(v) if v else None)
                for k, v in (("image_col", args.image_col), ("text_col", args.text_col), ("audio_col", args.audio_col))}

        # 4-5. Chạy inspector + Spotlight
        insp = UniversalDataInspector(
            df, dataset_name, output_root=OUTPUT_DIR, contamination=args.contamination, **cols
        )
        insp.detect()
        paths = insp.save_reports()
        print(f"\n✔ Kết quả đã lưu tại: {paths['report'].parent}")
        if not args.no_ui:
            insp.launch_spotlight(port=args.port)
        return 0

    except KeyboardInterrupt:
        log.info("Đã dừng theo yêu cầu người dùng.")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        log.error("%s", e)
        return 1
    except Exception:
        log.exception("Lỗi không mong đợi")
        return 2


if __name__ == "__main__":
    sys.exit(main())
