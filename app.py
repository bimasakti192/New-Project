import base64
import re
from io import BytesIO

import cv2
import numpy as np
import pandas as pd
from PIL import Image
import requests
import speech_recognition as sr
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st
import torch
import torchvision.models as models
import torchvision.transforms as transforms

# ==============================================================================
# 🔗 LINK CSV GOOGLE SHEETS
# ==============================================================================
DATABASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTcS0mSoo1HwqTihRlqwwhyxJSpVMW4WH15XM_rx2yLGfXCjbOn-SbEetgs5vRn8OWEFqO_ov-BgMwP/pub?output=csv"
# ==============================================================================

st.set_page_config(page_title="Katalog Komponen", layout="wide")

# --- CSS: SEARCH BAR STYLE (PILL / ROUNDED SEPERTI CHAT BAR) --------------
st.markdown(
    """
    <style>
    /* Bar utama dibungkus st.container(border=True, key="search_bar") */
    .st-key-search_bar {
        border-radius: 28px !important;
        border: 1px solid #e5e5e5 !important;
        padding: 6px 14px !important;
        background: #ffffff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    /* Hilangkan border bawaan text_input, biar menyatu dengan pill */
    .st-key-search_bar div[data-testid="stTextInput"] input {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        font-size: 15px;
    }
    .st-key-search_bar div[data-testid="stTextInput"] > div {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    /* Tombol "+" jadi bulat */
    .st-key-search_bar .st-key-btn_plus button {
        border-radius: 50% !important;
        width: 38px;
        height: 38px;
        padding: 0 !important;
        font-size: 16px;
    }
    /* Tombol mic jadi bulat */
    .st-key-search_bar .st-key-btn_mic button {
        border-radius: 50% !important;
        width: 38px;
        height: 38px;
        padding: 0 !important;
        font-size: 16px;
    }
    /* Tombol aksi (reset) jadi bulat, aksen oranye seperti tombol kirim */
    .st-key-search_bar .st-key-btn_reset button {
        border-radius: 50% !important;
        width: 38px;
        height: 38px;
        padding: 0 !important;
        background-color: #d97757 !important;
        color: white !important;
        border: none !important;
        font-size: 16px;
    }
    .st-key-search_bar .st-key-btn_reset button:hover {
        background-color: #c2664a !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- 1. CACHE MODEL & PREPROCESSING ---
@st.cache_resource
def load_feature_extractor():
  weights = models.ResNet18_Weights.DEFAULT
  model = models.resnet18(weights=weights)
  model = torch.nn.Sequential(*list(model.children())[:-1])
  model.eval()
  return model


model = load_feature_extractor()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
    ),
])


# --- 2. CACHE DATABASE ---
@st.cache_data(ttl=300, show_spinner=False)
def load_database(url):
  df_raw = pd.read_csv(url)
  df_clean = df_raw.fillna("")
  return df_raw, df_clean


# --- 3. CACHE UNDUH GAMBAR ---
def get_drive_direct_url(drive_url):
  file_id_match = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]+)", str(drive_url))
  if file_id_match:
    file_id = file_id_match.group(1)
    return f"https://lh3.googleusercontent.com/d/{file_id}"
  return drive_url


@st.cache_data(show_spinner=False)
def load_image_from_url(url):
  try:
    direct_url = get_drive_direct_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(direct_url, headers=headers, timeout=5)
    if response.status_code == 200:
      return Image.open(BytesIO(response.content))
  except Exception:
    pass
  return None


def auto_crop_object(image, margin_ratio=0.06):
  """Memotong area di luar objek utama pakai GrabCut, lebih tahan
  terhadap background yang bervariasi/tidak konsisten dibanding
  threshold sederhana. Mengembalikan gambar asli jika deteksi gagal
  atau tidak meyakinkan (bukan error, tapi fallback aman)."""
  try:
    img_rgb = np.array(image.convert("RGB"))
    h, w = img_rgb.shape[:2]
    if h < 10 or w < 10:
      return image

    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    # Asumsi awal: objek utama berada di area tengah foto.
    mw, mh = max(int(w * 0.08), 1), max(int(h * 0.08), 1)
    rect = (mw, mh, max(w - 2 * mw, 1), max(h - 2 * mh, 1))

    cv2.grabCut(
        img_rgb, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT
    )
    fg_mask = np.where((mask == 2) | (mask == 0), 0, 1).astype("uint8")
    ys, xs = np.where(fg_mask == 1)
    if len(xs) == 0 or len(ys) == 0:
      return image

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    box_w, box_h = x1 - x0, y1 - y0
    area_ratio = (box_w * box_h) / (w * h)

    # Jika area terdeteksi terlalu kecil/besar, hasil dianggap tidak
    # meyakinkan -> pakai gambar asli sebagai fallback.
    if area_ratio < 0.03 or area_ratio > 0.98:
      return image

    mx, my = int(box_w * margin_ratio), int(box_h * margin_ratio)
    x0c, y0c = max(x0 - mx, 0), max(y0 - my, 0)
    x1c, y1c = min(x1 + mx, w), min(y1 + my, h)
    return image.crop((x0c, y0c, x1c, y1c))
  except Exception:
    return image


def pad_to_square(image, fill=(255, 255, 255)):
  """Menambahkan padding agar rasio bentuk objek tidak melar/gepeng
  saat di-resize ke ukuran persegi untuk CNN."""
  w, h = image.size
  size = max(w, h)
  canvas = Image.new("RGB", (size, size), fill)
  canvas.paste(image, ((size - w) // 2, (size - h) // 2))
  return canvas


def compute_color_histogram(image, grid=3, bins=8):
  """Histogram warna HSV per-grid, supaya posisi warna pada objek
  (bukan cuma rata-rata warna) ikut diperhitungkan."""
  resized = np.array(image.resize((90, 90)).convert("RGB"))
  hsv = cv2.cvtColor(resized, cv2.COLOR_RGB2HSV)
  h, w, _ = hsv.shape
  cell_h, cell_w = h // grid, w // grid

  feats = []
  for i in range(grid):
    for j in range(grid):
      cell = hsv[
          i * cell_h : (i + 1) * cell_h, j * cell_w : (j + 1) * cell_w
      ]
      hist = cv2.calcHist([cell], [0, 1], None, [bins, bins], [0, 180, 0, 256])
      hist = cv2.normalize(hist, hist).flatten()
      feats.append(hist)
  return np.concatenate(feats)


def extract_features(image):
  if image.mode != "RGB":
    image = image.convert("RGB")
  img_t = transform(image).unsqueeze(0)
  with torch.no_grad():
    features = model(img_t)
  return features.squeeze().numpy()


def extract_combined_features(image):
  """Menghasilkan fitur bentuk (CNN) & warna (histogram spasial) dari
  DUA varian gambar: hasil crop objek, dan gambar penuh apa adanya.
  Dua varian ini dipakai sebagai jaring pengaman: kalau crop meleset
  di satu sisi (query atau database), varian gambar penuh tetap bisa
  menangkap kecocokan yang sebenarnya."""
  full_squared = pad_to_square(image)
  crop_squared = pad_to_square(auto_crop_object(image))

  return {
      "shape_full": extract_features(full_squared),
      "color_full": compute_color_histogram(full_squared),
      "shape_crop": extract_features(crop_squared),
      "color_crop": compute_color_histogram(crop_squared),
  }


@st.cache_data(show_spinner=False)
def get_cached_combined_features(url):
  img = load_image_from_url(url)
  if img:
    return extract_combined_features(img)
  return None


def normalize_text(text):
  if pd.isna(text):
    return ""
  return re.sub(r"[\s\-]+", "", str(text)).lower()


# --- STATE MANAGEMENT ---
if "search_input" not in st.session_state:
  st.session_state["search_input"] = ""
if "photo_key" not in st.session_state:
  st.session_state["photo_key"] = 0
if "last_audio_id" not in st.session_state:
  st.session_state["last_audio_id"] = None


def transcribe_audio(audio_file, language="id-ID"):
  """Mengubah rekaman suara (WAV dari st.audio_input) menjadi teks."""
  recognizer = sr.Recognizer()
  try:
    with sr.AudioFile(audio_file) as source:
      audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data, language=language)
  except sr.UnknownValueError:
    return None
  except sr.RequestError:
    return "__ERROR__"


def clear_photo():
  st.session_state["photo_key"] += 1


def reset_search():
  st.session_state["search_input"] = ""
  clear_photo()


# --- BACA DATABASE ---
try:
  df_raw, df_clean = load_database(DATABASE_URL)
except Exception as e:
  st.error(f"Gagal memuat spreadsheet: {e}")
  st.stop()

photo_cols = [
    c
    for c in df_raw.columns
    if any(kw in c.lower() for kw in ["link", "foto", "drive", "url"])
]

# --- UI HEADER & INPUT BAR ---
st.title("Pencarian & Katalog Komponen")

uploaded_file = None
captured_image = None

# Frame Bar Input Utama — gaya pill/rounded
with st.container(border=True, key="search_bar"):
  col_plus, col_search, col_mic, col_reset = st.columns(
      [0.7, 7, 0.7, 0.7], vertical_alignment="center"
  )

  # 1. MENU POPUP (+) -> hanya opsi foto
  with col_plus:
    with st.popover("➕", help="Tambah foto acuan", use_container_width=True):
      st.markdown("📎 **Opsi Foto**")

      with st.expander("⚙️ Pengaturan Pencocokan Gambar"):
        st.slider(
            "Fokus Bentuk ↔ Warna",
            min_value=0.0,
            max_value=1.0,
            value=0.6,
            step=0.05,
            key="shape_weight",
            help=(
                "Geser ke kiri untuk lebih mengutamakan warna, ke kanan"
                " untuk lebih mengutamakan bentuk objek."
            ),
        )

      option = st.radio(
          "Pilih Opsi",
          ["Upload File", "Ambil Foto"],
          label_visibility="collapsed",
          key="photo_option",
      )
      if option == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload Gambar",
            type=["jpg", "png", "jpeg"],
            key=f"upload_{st.session_state['photo_key']}",
        )
      elif option == "Ambil Foto":
        captured_image = st.camera_input(
            "Ambil Foto", key=f"camera_{st.session_state['photo_key']}"
        )

  # 2. KOLOM TEXT SEARCH GLOBAL
  with col_search:
    search_query = st.text_input(
        "Pencarian Global",
        key="search_input",
        placeholder="Ketik kata kunci pencarian...",
        label_visibility="collapsed",
    )

  # 3. TOMBOL MIC -> rekam suara native (bukan iframe) lalu transkripsi
  with col_mic:
    with st.popover("🎤", help="Cari dengan suara", use_container_width=True):
      st.caption("Tekan rekam, ucapkan kata kunci, lalu tekan stop.")
      audio_value = st.audio_input(
          "Rekam suara", label_visibility="collapsed"
      )
      if audio_value is not None:
        audio_hash = hash(audio_value.getvalue())
        if audio_hash != st.session_state["last_audio_id"]:
          st.session_state["last_audio_id"] = audio_hash
          with st.spinner("Mengubah suara menjadi teks..."):
            text = transcribe_audio(audio_value)
          if text == "__ERROR__":
            st.error(
                "Gagal terhubung ke layanan pengenalan suara. Cek koneksi"
                " internet."
            )
          elif text:
            st.session_state["search_input"] = text
            st.rerun()
          else:
            st.warning("Suara tidak terdengar jelas, coba rekam ulang.")

  # 4. TOMBOL RESET (ikon bulat aksen oranye)
  with col_reset:
    st.button(
        "✕",
        help="Hapus Semua",
        on_click=reset_search,
        use_container_width=True,
        key="btn_reset",
    )

active_photo = uploaded_file or captured_image
active_text_query = search_query.strip()

# --- PRATINJAU FOTO & TOMBOL HAPUS (❌) ---
if active_photo:
  with st.container(border=True):
    col_img_thumb, col_img_btn = st.columns(
        [1, 1], vertical_alignment="center"
    )
    with col_img_thumb:
      st.image(active_photo, width=90)
    with col_img_btn:
      st.button(
          "❌",
          on_click=clear_photo,
          type="secondary",
          key="btn_hapus_foto_acuan",
      )

st.markdown("---")

# --- PROSES PEMROSESAN HASIL PENCARIAN ---
if not active_text_query and not active_photo:
  st.subheader("Selamat datang!")
  st.info(
      "Silakan ketik kata kunci pada kolom pencarian, atau klik ikon **➕** untuk"
      " memilih opsi foto, atau ikon **🎤** untuk mencari dengan suara."
  )
else:
  filtered_df = df_clean.copy()

  # Pencarian Teks Global (Semua Kolom)
  if active_text_query:
    norm_query = normalize_text(active_text_query)
    mask = (
        filtered_df.astype(str)
        .apply(
            lambda row: row.apply(lambda val: norm_query in normalize_text(val))
        )
        .any(axis=1)
    )
    filtered_df = filtered_df[mask]

  # Pencarian Gambar AI (kombinasi kemiripan bentuk + warna)
  if active_photo:
    shape_weight = st.session_state.get("shape_weight", 0.6)
    color_weight = 1.0 - shape_weight

    with st.spinner("Menganalisis kemiripan objek (bentuk & warna)..."):
      query_image = Image.open(active_photo)
      query_feat = extract_combined_features(query_image)

      similarities = []
      shape_scores = []
      color_scores = []
      loaded_images_dict = []

      for idx, row in filtered_df.iterrows():
        max_sim = -1
        best_shape_sim = 0.0
        best_color_sim = 0.0
        row_images = []

        for p_col in photo_cols:
          drive_url = str(row.get(p_col, "")).strip()
          if drive_url:
            db_feat = get_cached_combined_features(drive_url)
            if db_feat is not None:
              # Bandingkan semua kombinasi varian crop/full (query x db)
              # dan ambil yang terbaik -> jaring pengaman kalau crop
              # meleset di salah satu sisi.
              sim_shape = max(
                  cosine_similarity(
                      [query_feat[qk]], [db_feat[dk]]
                  )[0][0]
                  for qk in ("shape_crop", "shape_full")
                  for dk in ("shape_crop", "shape_full")
              )
              sim_color = max(
                  cosine_similarity(
                      [query_feat[qk]], [db_feat[dk]]
                  )[0][0]
                  for qk in ("color_crop", "color_full")
                  for dk in ("color_crop", "color_full")
              )
              combined_sim = (
                  shape_weight * sim_shape + color_weight * sim_color
              )
              if combined_sim > max_sim:
                max_sim = combined_sim
                best_shape_sim = sim_shape
                best_color_sim = sim_color

            img = load_image_from_url(drive_url)
            if img:
              row_images.append(img)

        similarities.append(max_sim)
        shape_scores.append(best_shape_sim)
        color_scores.append(best_color_sim)
        loaded_images_dict.append(row_images)

      filtered_df["Tingkat Kemiripan (%)"] = [
          round(s * 100, 2) if s >= 0 else 0 for s in similarities
      ]
      filtered_df["Kemiripan Bentuk (%)"] = [
          round(s * 100, 2) for s in shape_scores
      ]
      filtered_df["Kemiripan Warna (%)"] = [
          round(s * 100, 2) for s in color_scores
      ]
      filtered_df["Loaded_Images"] = loaded_images_dict

      results_df = filtered_df.sort_values(
          by="Tingkat Kemiripan (%)", ascending=False
      )
  else:
    results_df = filtered_df

  # Tampilan Data Output
  if results_df.empty:
    st.warning("Tidak ada data barang yang sesuai dengan pencarian Anda.")
  else:
    EXCLUDE_KEYWORDS = [
        "link",
        "foto",
        "drive",
        "url",
        "uom",
        "loaded_images",
        "tingkat kemiripan (%)",
        "kemiripan bentuk (%)",
        "kemiripan warna (%)",
    ]

    for index, row in results_df.iterrows():
      with st.container():
        col_foto, col_detail = st.columns([1, 3.5])

        with col_foto:
          imgs = row.get("Loaded_Images", [])
          if not active_photo:
            imgs = []
            for p_col in photo_cols:
              drive_url = str(row.get(p_col, "")).strip()
              if drive_url:
                img = load_image_from_url(drive_url)
                if img:
                  imgs.append(img)

          if imgs:
            for img in imgs:
              st.image(img, width=130)
          else:
            st.caption("Tanpa Foto")

        with col_detail:
          for col in df_raw.columns:
            col_clean = col.strip()
            col_lower = col_clean.lower()

            if any(kw in col_lower for kw in EXCLUDE_KEYWORDS):
              continue

            val = str(row.get(col, "")).strip()
            val_display = val if val else "-"

            if col_lower == "qty":
              uom_col = next(
                  (c for c in df_raw.columns if c.strip().lower() == "uom"),
                  None,
              )
              uom_val = (
                  str(row.get(uom_col, "")).strip() if uom_col else ""
              )
              st.markdown(f"**{col_clean} :** {val_display} {uom_val}".strip())
            else:
              st.markdown(f"**{col_clean} :** {val_display}")

          if (
              "Tingkat Kemiripan (%)" in row
              and row["Tingkat Kemiripan (%)"] > 0
          ):
            st.markdown(
                f"**Kemiripan Foto :** {row['Tingkat Kemiripan (%)']}%"
                f" &nbsp;·&nbsp; Bentuk: {row['Kemiripan Bentuk (%)']}%"
                f" &nbsp;·&nbsp; Warna: {row['Kemiripan Warna (%)']}%"
            )

      st.divider()
