# Pretrain – Universal Data Inspector

Công cụ tự động **phát hiện dữ liệu lỗi / bất thường (outlier)** trong dataset bất kỳ
(CSV, Parquet, Excel, JSON, thư mục ảnh/audio), xuất **báo cáo ảnh tĩnh chấm đỏ**,
tách **tập dữ liệu sạch**, và mở **Web UI tương tác 100% offline** bằng
[Renumics Spotlight](https://github.com/Renumics/spotlight).

- Thuật toán: **ECOD** (PyOD) – không cần tinh chỉnh tham số, nhanh, giải thích được.
- Chạy hoàn toàn local, không gọi dịch vụ ngoài.

---

## 1. Cấu trúc thư mục

```
Pretrain/
├── data/input/              ← ĐẶT DỮ LIỆU ĐẦU VÀO VÀO ĐÂY
├── preprocess.py            ← Tiền xử lý riêng cho từng dataset (SỬA FILE NÀY)
├── inspector.py             ← Lõi: ECOD + vẽ biểu đồ + xuất file + Spotlight (cố định)
├── run.py                   ← CLI điều khiển chính (CHẠY FILE NÀY)
├── requirements.txt
├── README.md
└── outputs/
    └── <tên_dataset>/
        ├── data_clean.csv           # dữ liệu sạch (đã loại outlier)
        ├── data_report.csv          # toàn bộ dữ liệu + is_outlier, outlier_score, status
        └── data_health_report.png   # biểu đồ tĩnh, chấm đỏ = lỗi
```

`<tên_dataset>` lấy từ tên file (`houses.csv` → `outputs/houses/`) hoặc tên thư mục.

---

## 2. Cài đặt

Yêu cầu **Python 3.9 – 3.11** (Spotlight chưa hỗ trợ 3.12+).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
python -m pip install -r requirements.txt
```

---

## 3. Cách chạy

```bash
python run.py data/input/<tên_file.csv> [tùy chọn]
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `input` | File dữ liệu hoặc thư mục ảnh/audio (có thể chỉ cần tên file trong `data/input/`) | bắt buộc |
| `--image_col` | Cột chứa đường dẫn ảnh | tự nhận diện theo đuôi file |
| `--audio_col` | Cột chứa đường dẫn audio | tự nhận diện |
| `--text_col` | Cột văn bản | – |
| `--port` | Cổng Spotlight | tự chọn |
| `--contamination` | Tỉ lệ outlier kỳ vọng, trong (0, 0.5) | `0.05` |
| `--no_ui` | Chỉ xuất báo cáo, không mở Spotlight | tắt |

Ví dụ:

```bash
python run.py data/input/houses.csv
python run.py data/input/products.csv --image_col image_path --text_col description --port 8080
python run.py data/input/photos            # thư mục ảnh
python run.py data/input/houses.csv --no_ui --contamination 0.1
```

Sau khi chạy, mở `http://localhost:<port>` (trình duyệt tự bật). Dừng bằng `Ctrl+C`.
Trong Spotlight, chọn **Color by → `status`** để thấy điểm đỏ (lỗi) / xanh (sạch);
click vào một điểm để xem ảnh, text, audio tương ứng.

---

## 4. Luồng xử lý

```
 data/input/<file>
        │
        ▼
 [run.py] load_input()          đọc csv/parquet/xlsx/json hoặc quét thư mục media
        │                       (thư mục: trích width, height, brightness, duration... )
        ▼
 [preprocess.py]                chuẩn hóa tên cột, bỏ dòng trùng/rỗng, ép kiểu số/thời gian,
 preprocess_data()              giải đường dẫn ảnh/audio → tuyệt đối, + logic tùy biến
        │
        ▼
 [inspector.py] detect()        chọn cột số (bỏ cột hằng/toàn NaN, điền NaN bằng median)
        │                       → ECOD(contamination) → outlier_score, is_outlier, status
        │                       → PCA 2D (map_x, map_y) để vẽ bản đồ
        ▼
 [inspector.py] save_reports()  data_report.csv · data_clean.csv · data_health_report.png
        │
        ▼
 [inspector.py] launch_spotlight()   Web UI offline tại localhost
```

### Chi tiết từng bước

1. **Đọc dữ liệu** – `run.py` tự chọn reader theo đuôi file; CSV tự dò dấu phân cách và
   thử `utf-8-sig` rồi `latin-1`. Ảnh hỏng được ghi nhận là dòng lỗi (các đặc trưng = 0).
2. **Tiền xử lý** – tên cột bỏ dấu tiếng Việt, về chữ thường, `snake_case`. Cột chữ có ≥ 90%
   giá trị parse được thành số sẽ được ép sang số; cột có tên gợi ý thời gian
   (`date`, `time`, `ngay`…) được chuyển sang datetime rồi thêm cột `*_ts` (epoch giây).
3. **Chấm điểm** – ECOD ước lượng phân phối đuôi trên từng cột số; điểm càng cao càng bất
   thường. `contamination` quyết định tỉ lệ mẫu bị gắn cờ.
4. **Báo cáo ảnh** – subplot trái: histogram `outlier_score` + ngưỡng lỗi; subplot phải:
   scatter PCA 2D, sạch = xanh, lỗi = đỏ viền đen.
5. **Spotlight** – `status`, `is_outlier`, `outlier_score` đều có trong bảng để lọc/sắp xếp;
   cột ảnh → `spotlight.Image`, audio → `spotlight.Audio`.

---

## 5. Cột đầu ra

| Cột | Ý nghĩa |
|---|---|
| `outlier_score` | Điểm bất thường (cao = đáng nghi) |
| `is_outlier` | `True` nếu bị gắn cờ lỗi |
| `status` | `LỖI / OUTLIER` hoặc `SẠCH` |

`data_clean.csv` giữ nguyên các cột gốc (đã tiền xử lý), **không** có các cột trên.
File CSV ghi bằng `utf-8-sig` để Excel đọc đúng tiếng Việt.

---

## 6. Sửa và tinh chỉnh

> Với dữ liệu bảng có cột số thông thường, **không cần sửa gì**: bỏ file vào `data/input/`
> rồi chạy `python run.py data/input/<file>`. Mục này dành cho khi kết quả chưa như ý.

### 6.1. Chỉnh bằng tham số CLI (không cần sửa code)

| Mục tiêu | Cách làm |
|---|---|
| Ít điểm đỏ hơn (dữ liệu khá sạch) | `--contamination 0.01` |
| Nhiều điểm đỏ hơn (dữ liệu bẩn) | `--contamination 0.1` (phải < 0.5) |
| Hiện ảnh trong Spotlight | `--image_col TÊN_CỘT` |
| Hiện audio | `--audio_col TÊN_CỘT` |
| Hiện nội dung văn bản | `--text_col TÊN_CỘT` |
| Cổng bị chiếm | `--port 8080` |
| Chỉ lấy báo cáo, không bật UI | `--no_ui` |

Tên cột truyền vào được tự chuẩn hóa giống tên trong dữ liệu
(`"Ảnh Sản Phẩm"` → `anh_san_pham`), nên gõ tên gốc hay tên đã chuẩn hóa đều được.

### 6.2. Sửa `preprocess.py` cho dataset riêng

Mở `preprocess.py`, kéo xuống cuối hàm `preprocess_data`, thêm code vào khu vực
**"TÙY BIẾN THEO DATASET"**. Lúc này `df` đã có tên cột chuẩn hóa
(chữ thường, không dấu, `snake_case`) và đã bỏ dòng trùng.

```python
# --- Loại giá trị vô lý trước khi chấm điểm ---
df = df[df["price"] > 0]
df = df[df["age"].between(0, 120)]

# --- Giảm lệch phân phối (cột đuôi dài như giá, diện tích) ---
df["price_log"] = np.log1p(df["price"])

# --- Bỏ cột định danh / không mang ý nghĩa thống kê ---
df = df.drop(columns=["id", "uuid"], errors="ignore")

# --- Tạo đặc trưng số từ cột chữ (để ECOD xét được cả cột text) ---
df["text_len"] = df["description"].fillna("").str.len()
df["n_words"]  = df["description"].fillna("").str.split().str.len()

# --- Mã hóa cột phân loại ít giá trị thành số ---
df["city_code"] = df["city"].astype("category").cat.codes

# --- Đặc trưng từ thời gian ---
df["hour"] = pd.to_datetime(df["created_at"], errors="coerce").dt.hour
```

Quy tắc: **ECOD chỉ xét cột số**. Muốn cột chữ/ảnh/audio góp phần phát hiện lỗi,
hãy tạo cột số mô tả nó (độ dài, kích thước, thời lượng, embedding…).

### 6.3. Tình huống thường gặp

| Tình huống | Cách xử lý |
|---|---|
| Cột số bị đọc thành chữ (`"1.200,5"`, `"$12"`) | `df["x"] = pd.to_numeric(df["x"].str.replace(r"[^\d.]", "", regex=True), errors="coerce")` |
| Cột nhãn/ID dạng số gây nhiễu | `df = df.drop(columns=["label"])` hoặc `df["label"] = df["label"].astype(str)` (vẫn xem được trong UI, không bị chấm điểm) |
| Đường dẫn ảnh nằm ngoài `data/input` | `df["img"] = r"D:\anh" + "\\" + df["file_name"]` |
| Ảnh/audio nằm trong thư mục, không có CSV | `python run.py data/input/photos` |
| Dataset quá lớn, chạy chậm | `df = df.sample(50000, random_state=0)` |
| Muốn thêm đặc trưng cho ảnh | Sửa `_media_folder_to_df` trong `run.py` (độ nét, histogram màu…) |

### 6.4. Chỉnh sâu trong `inspector.py` (tùy chọn)

| Muốn đổi | Vị trí |
|---|---|
| Thuật toán khác (IForest, COPOD, LOF…) | Hàm `detect()`: đổi import và dòng `ECOD(contamination=...)`, ví dụ `from pyod.models.iforest import IForest`. ECOD/COPOD nhanh nhất; IForest/LOF bắt được lỗi tương quan giữa các cột |
| Màu chấm | Hằng số `COLOR_OK`, `COLOR_BAD` |
| Kích thước, độ phân giải ảnh | `figsize` và `dpi` trong `_plot()` |
| Cách chiếu 2D (UMAP, t-SNE thay PCA) | Hàm `_project_2d()` |
| Nhãn trạng thái | Hằng số `STATUS_BAD`, `STATUS_OK` |

Sau mỗi lần sửa, chạy `python run.py <file> --no_ui` để kiểm tra nhanh báo cáo
trước khi mở UI.

### 6.5. Ví dụ sửa code hoàn chỉnh (copy – dán)

Tất cả ví dụ dưới đây đều dán vào **khu vực "TÙY BIẾN THEO DATASET"** của
`preprocess_data` trong [preprocess.py](preprocess.py), ngay trước dòng `return df`
(trừ ví dụ F, G sửa `inspector.py`). `np`, `pd`, `Path` đã được import sẵn.

#### A. Dataset bảng (giá nhà, doanh số, cảm biến…)

File `data/input/houses.csv` có cột `Giá`, `Diện tích`, `Số phòng`, `ID`, `Ngày đăng`.
Sau chuẩn hóa tên cột chúng là `gia`, `dien_tich`, `so_phong`, `id`, `ngay_dang`.

```python
    # Bỏ cột ID (không mang ý nghĩa thống kê)
    df = df.drop(columns=["id"], errors="ignore")

    # Loại dòng giá/diện tích <= 0 (chắc chắn là lỗi nhập liệu)
    df = df[(df["gia"] > 0) & (df["dien_tich"] > 0)]

    # Thêm đặc trưng dẫn xuất: giá trên mét vuông -> bắt được "giá rẻ/đắt bất thường"
    df["gia_m2"] = df["gia"] / df["dien_tich"]

    # Giảm lệch phân phối của cột đuôi dài
    df["gia_log"] = np.log1p(df["gia"])

    df = df.reset_index(drop=True)   # luôn reset index sau khi lọc dòng
```

Chạy: `python run.py data/input/houses.csv`

#### B. Dataset ảnh có file CSV (cột `image_path`, `label`)

Ảnh không có cột số sẵn, nên phải **trích đặc trưng số từ ảnh**: kích thước,
độ sáng, độ tương phản, độ nét. Ảnh hỏng/thiếu cũng bị gắn là lỗi.

```python
    from PIL import Image, ImageFilter

    def _img_features(path):
        try:
            with Image.open(path) as im:
                g = im.convert("L")
                a = np.asarray(g, dtype=float)
                edges = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=float)
                return pd.Series({
                    "img_w": im.width, "img_h": im.height,
                    "img_brightness": a.mean(), "img_contrast": a.std(),
                    "img_sharpness": edges.var(),          # thấp = ảnh mờ
                    "img_ok": 1,
                })
        except Exception:                                   # ảnh hỏng / không tồn tại
            return pd.Series({"img_w": 0, "img_h": 0, "img_brightness": 0,
                              "img_contrast": 0, "img_sharpness": 0, "img_ok": 0})

    feats = df["image_path"].apply(_img_features)
    df = pd.concat([df, feats], axis=1)

    # Nhãn dạng số (0/1/2...) không nên bị chấm điểm -> đổi sang chuỗi
    df["label"] = df["label"].astype(str)
```

Chạy: `python run.py data/input/images.csv --image_col image_path`

#### C. Dataset văn bản (cột `content`)

```python
    txt = df["content"].fillna("").astype(str)
    df["txt_chars"]   = txt.str.len()
    df["txt_words"]   = txt.str.split().str.len()
    df["txt_upper"]   = txt.str.count(r"[A-ZÀ-Ỵ]") / txt.str.len().clip(lower=1)
    df["txt_digits"]  = txt.str.count(r"\d") / txt.str.len().clip(lower=1)
    df["txt_special"] = txt.str.count(r"[^\w\s]") / txt.str.len().clip(lower=1)
    df["txt_empty"]   = (txt.str.strip() == "").astype(int)
```

Chạy: `python run.py data/input/reviews.csv --text_col content`

#### D. Dataset audio (thư mục `.wav`)

Không cần sửa code: `python run.py data/input/audio_folder` sẽ tự trích
`file_size` và `duration_sec`. Muốn thêm đặc trưng (RMS, tần số…), sửa
`_media_folder_to_df` trong [run.py](run.py), nhánh `elif ext in AUDIO_EXT:`:

```python
            rms = 0.0
            if ext == ".wav":
                try:
                    import numpy as np
                    with wave.open(str(p)) as w:
                        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                        rms = float(np.sqrt(np.mean(raw.astype(float) ** 2))) if raw.size else 0.0
                except Exception:
                    pass
            rows.append({"audio_path": str(p), "file_size": p.stat().st_size,
                         "duration_sec": dur, "rms": rms})
```

(thay cho dòng `rows.append({"audio_path": ...})` hiện có.)

#### E. Đổi thuật toán phát hiện (sửa `inspector.py`, hàm `detect`)

Tìm đoạn:

```python
        from pyod.models.ecod import ECOD
        ...
        model = ECOD(contamination=self.contamination)
```

Đổi thành (ví dụ Isolation Forest – bắt được lỗi do tổ hợp nhiều cột):

```python
        from pyod.models.iforest import IForest
        ...
        model = IForest(contamination=self.contamination, random_state=0)
```

Các lựa chọn khác, cùng giao diện `fit` / `decision_scores_` / `labels_`:

| Thuật toán | Import | Khi nào dùng |
|---|---|---|
| ECOD (mặc định) | `pyod.models.ecod.ECOD` | Nhanh, không tham số, lỗi nằm trên từng cột |
| COPOD | `pyod.models.copod.COPOD` | Tương tự ECOD |
| IForest | `pyod.models.iforest.IForest` | Dữ liệu nhiều cột, lỗi do kết hợp bất thường |
| LOF | `pyod.models.lof.LOF` | Lỗi cục bộ trong cụm; chậm với dữ liệu lớn |
| KNN | `pyod.models.knn.KNN` | Dữ liệu nhỏ/vừa |

Không cần sửa chỗ nào khác; các hàm vẽ và xuất file dùng chung kết quả.

#### F. Đổi giao diện biểu đồ (sửa `inspector.py`)

```python
COLOR_OK = "#2ca02c"     # xanh lá thay vì xanh dương
COLOR_BAD = "#ff0000"    # đỏ thuần
```

Trong `_plot()`: `figsize=(15, 6)` đổi kích thước, `fig.savefig(path, dpi=150)` đổi độ nét,
`bins=50` đổi số cột histogram, `s=60` đổi độ lớn chấm đỏ.

#### G. Đổi PCA sang t-SNE cho bản đồ 2D (sửa `inspector.py`, hàm `_project_2d`)

Thay phần thân sau dòng `Xs = StandardScaler().fit_transform(X)`:

```python
        if Xs.shape[1] == 1:
            return Xs[:, 0], np.arange(len(Xs), dtype=float)
        from sklearn.manifold import TSNE
        perp = max(5, min(30, len(Xs) // 4))
        coords = TSNE(n_components=2, perplexity=perp, random_state=0).fit_transform(Xs)
        return coords[:, 0], coords[:, 1]
```

t-SNE chậm với > 10 000 dòng; khi đó giữ PCA hoặc lấy mẫu dữ liệu trước.

#### H. Cách kiểm tra sau khi sửa

```bash
python run.py data/input/<file> --no_ui     # nhanh, không mở UI
```

Mở `outputs/<tên_dataset>/data_report.csv`, sắp xếp giảm dần theo `outlier_score` và đọc
vài dòng đầu: nếu chúng thật sự là dữ liệu lỗi thì cấu hình đã đúng; nếu toàn dòng
bình thường, hãy thêm/đổi đặc trưng số (ví dụ A–C) hoặc đổi thuật toán (E).

---

## 7. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `Không có cột số nào dùng được` | Dataset chỉ có cột chữ → ép kiểu trong `preprocess.py` |
| `ModuleNotFoundError: renumics` | `pip install renumics-spotlight` (cần Python ≤ 3.11) |
| Ảnh không hiện trong Spotlight | Kiểm tra đường dẫn ảnh tồn tại; truyền `--image_col` |
| Quá nhiều / quá ít điểm đỏ | Điều chỉnh `--contamination` |
| Tiếng Việt lỗi trong console | Đã ép UTF-8; dùng Windows Terminal nếu vẫn lỗi font |

## 8. Hạn chế

- Phát hiện outlier chỉ dựa trên **cột số**; cột chữ/ảnh/audio chỉ để hiển thị, trừ khi được
  trích đặc trưng số (ví dụ embedding) trong `preprocess.py`.
- ECOD giả định các cột độc lập; lỗi dạng tương quan giữa nhiều cột có thể bị bỏ sót.
