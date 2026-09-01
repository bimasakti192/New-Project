import base64
import re
from io import BytesIO

import pandas as pd
from PIL import Image
import requests
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st
from streamlit_mic_recorder import mic_recorder
import torch
import torchvision.models as models
import torchvision.transforms as transforms

# ==============================================================================
# 🔗 LINK CSV GOOGLE SHEETS
# ==============================================================================
DATABASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTcS0mSoo1HwqTihRlqwwhyxJSpVMW4WH15XM_rx2yLGfXCjbOn-SbEetgs5vRn8OWEFqO_ov-BgMwP/pub?output=csv"
# ==============================================================================

st.set_page_config(page_title="Katalog Komponen", layout="wide")


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


def extract_features(image):
  if image.mode != "RGB":
    image = image.convert("RGB")
  img_t = transform(image).unsqueeze(0)
  with torch.no_grad():
    features = model(img_t)
  return features.squeeze().numpy()


@st.cache_data(show_spinner=False)
def get_cached_image_features(url):
  img = load_image_from_url(url)
  if img:
    return extract_features(img)
  return None


# --- 4. TRANSKRIPSI SUARA ---
def transcribe_audio_bytes(audio_bytes):
  try:
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    audio_file = BytesIO(audio_bytes)
    with sr.AudioFile(audio_file) as source:
      audio_data = recognizer.record(source)
      text = recognizer.recognize_google(audio_data, language="id-ID")
      return text
  except Exception:
    return None


def normalize_text(text):
  if pd.isna(text):
    return ""
  return re.sub(r"[\s\-]+", "", str(text)).lower()


# --- STATE MANAGEMENT ---
if "search_input" not in st.session_state:
  st.session_state["search_input"] = ""
if "voice_query" not in st.session_state:
  st.session_state["voice_query"] = ""


def reset_search():
  st.session_state["search_input"] = ""
  st.session_state["voice_query"] = ""


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

# --- UI HEADER & BAR PENCARIAN TERPADU ---
st.title("Pencarian & Katalog Komponen")

uploaded_file = None
captured_image = None

# Frame Bar Input Bergaya Gemini/ChatGPT
with st.container(border=True):
  col_plus, col_search, col_filter, col_reset = st.columns(
      [0.6, 5, 2, 0.8], vertical_alignment="center"
  )

  # 1. TOMBOL MENU MELAYANG (SEPERTI GEMINI/CHATGPT)
  with col_plus:
    with st.popover("➕", help="Tambah Lampiran & Opsi Input"):
      st.markdown("### 📎 Lampiran & Fitur Pencarian")

      tab_upload, tab_camera, tab_voice = st.tabs(
          ["📁 File", "📸 Kamera", "🎙️ Suara"]
      )

      with tab_upload:
        uploaded_file = st.file_uploader(
            "Upload Foto",
            type=["jpg", "png", "jpeg"],
            label_visibility="collapsed",
        )

      with tab_camera:
        captured_image = st.camera_input(
            "Ambil Foto", label_visibility="collapsed"
        )

      with tab_voice:
        st.write("Mulai rekam suara:")
        audio_record = mic_recorder(
            start_prompt="Mulai Bicara 🎙️",
            stop_prompt="Berhenti & Olah ⏹️",
            key="voice_recorder",
        )
        if audio_record is not None:
          audio_bytes = audio_record["bytes"]
          res_text = transcribe_audio_bytes(audio_bytes)
          if res_text:
            st.session_state["voice_query"] = res_text
            st.success(f'Terdengar: "{res_text}"')
          else:
            st.error("Suara kurang jelas/tidak terdeteksi.")

  # 2. KOLOM INPUT TEKS UTAMA
  with col_search:
    search_query = st.text_input(
        "Pencarian Global",
        key="search_input",
        placeholder="Ketik nama barang atau gunakan menu ➕...",
        label_visibility="collapsed",
    )

  # 3. FILTER KOLOM
  with col_filter:
    filter_column = st.selectbox(
        "Filter Kolom",
        options=["Semua Kolom"] + list(df_raw.columns),
        index=0,
        label_visibility="collapsed",
    )

  # 4. TOMBOL RESET
  with col_reset:
    st.button(
        "Reset",
        help="Hapus Pencarian",
        on_click=reset_search,
        use_container_width=True,
    )

active_photo = uploaded_file or captured_image
active_text_query = (
    search_query.strip()
    if search_query.strip()
    else st.session_state["voice_query"].strip()
)

st.markdown("---")

# --- PROSES HASIL PENCARIAN ---
if not active_text_query and not active_photo:
  st.subheader("Selamat datang!")
  st.info(
      "Silakan ketik kata kunci pada kolom pencarian, atau klik menu **➕** untuk"
      " mengambil foto atau merekam suara."
  )
else:
  filtered_df = df_clean.copy()

  # Pencarian Teks
  if active_text_query:
    norm_query = normalize_text(active_text_query)

    if filter_column == "Semua Kolom":
      mask = (
          filtered_df.astype(str)
          .apply(
              lambda row: row.apply(
                  lambda val: norm_query in normalize_text(val)
              )
          )
          .any(axis=1)
      )
    else:
      mask = filtered_df[filter_column].astype(str).apply(
          lambda val: norm_query in normalize_text(val)
      )
    filtered_df = filtered_df[mask]

  # Pencarian Gambar AI
  if active_photo:
    with st.spinner("Menganalisis kemiripan gambar..."):
      query_image = Image.open(active_photo)
      st.image(query_image, caption="Foto Acuan", width=120)
      query_features = extract_features(query_image)

      similarities = []
      loaded_images_dict = []

      for idx, row in filtered_df.iterrows():
        max_sim = -1
        row_images = []

        for p_col in photo_cols:
          drive_url = str(row.get(p_col, "")).strip()
          if drive_url:
            db_feat = get_cached_image_features(drive_url)
            if db_feat is not None:
              sim_score = cosine_similarity([query_features], [db_feat])[0][0]
              if sim_score > max_sim:
                max_sim = sim_score

            img = load_image_from_url(drive_url)
            if img:
              row_images.append(img)

        similarities.append(max_sim)
        loaded_images_dict.append(row_images)

      filtered_df["Tingkat Kemiripan (%)"] = [
          round(s * 100, 2) if s >= 0 else 0 for s in similarities
      ]
      filtered_df["Loaded_Images"] = loaded_images_dict

      filtered_df = filtered_df[filtered_df["Tingkat Kemiripan (%)"] >= 70]
      results_df = filtered_df.sort_values(
          by="Tingkat Kemiripan (%)", ascending=False
      )
  else:
    results_df = filtered_df

  # Tampilan Data
  if results_df.empty:
    if active_photo:
      st.warning(
          "Tidak ada barang yang cocok dengan tingkat kemiripan di atas 70%."
      )
    else:
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
            )

      st.divider()
