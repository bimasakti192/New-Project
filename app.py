import base64
import re
from io import BytesIO

import pandas as pd
from PIL import Image
import requests
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st
import streamlit.components.v1 as components
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


def normalize_text(text):
  if pd.isna(text):
    return ""
  return re.sub(r"[\s\-]+", "", str(text)).lower()


# --- STATE MANAGEMENT ---
if "search_input" not in st.session_state:
  st.session_state["search_input"] = ""
if "photo_key" not in st.session_state:
  st.session_state["photo_key"] = 0

# Tangkap hasil pencarian suara dari browser via Query Parameter
if "voice_search" in st.query_params:
  voice_text = st.query_params["voice_search"]
  st.session_state["search_input"] = voice_text
  st.query_params.clear()
  st.rerun()


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

VOICE_HTML = """
<div style="font-family: sans-serif; text-align: center; padding: 5px;">
    <p id="status" style="font-size: 13px; color: #555; margin-bottom: 8px;">
        Klik tombol di bawah dan langsung bicara.<br>Sistem akan <b>otomatis berhenti</b> saat Anda selesai bicara.
    </p>
    <button id="btn-mic" style="
        background-color: #d97757;
        color: white;
        border: none;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
        width: 100%;
        font-size: 14px;
    ">
        🎙️ Mulai Bicara
    </button>
</div>

<script>
const btn = document.getElementById('btn-mic');
const status = document.getElementById('status');

if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    status.innerHTML = "<b style='color:red;'>Browser tidak mendukung (Gunakan Chrome/Edge/Safari).</b>";
    btn.disabled = true;
} else {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'id-ID';
    recognition.continuous = false;
    recognition.interimResults = false;

    btn.onclick = () => {
        try {
            recognition.start();
        } catch(e) {}
    };

    recognition.onstart = () => {
        status.innerHTML = "<b style='color: green;'>🔴 Mendengarkan... Silakan bicara sekarang!</b>";
        btn.style.backgroundColor = "#28a745";
        btn.innerText = "🔊 Sedang Mendengarkan...";
    };

    recognition.onspeechend = () => {
        status.innerHTML = "⏳ Selesai bicara. Memproses...";
        recognition.stop();
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        status.innerHTML = "✅ Terdengar: <b>" + transcript + "</b>";
        const parentUrl = new URL(window.parent.location.href);
        parentUrl.searchParams.set('voice_search', transcript);
        window.parent.location.href = parentUrl.href;
    };

    recognition.onerror = (event) => {
        status.innerHTML = "<b style='color:red;'>Suara tidak terdeteksi. Coba lagi.</b>";
        btn.style.backgroundColor = "#d97757";
        btn.innerText = "🎙️ Mulai Bicara";
    };

    recognition.onend = () => {
        btn.style.backgroundColor = "#d97757";
        btn.innerText = "🎙️ Mulai Bicara";
    };
}
</script>
"""

# Frame Bar Input Utama — gaya pill/rounded
with st.container(border=True, key="search_bar"):
  col_plus, col_search, col_mic, col_reset = st.columns(
      [0.7, 7, 0.7, 0.7], vertical_alignment="center"
  )

  # 1. MENU POPUP (+) -> hanya opsi foto
  with col_plus:
    with st.popover("➕", help="Tambah foto acuan", use_container_width=True):
      st.markdown("📎 **Opsi Foto**")
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

  # 3. TOMBOL MIC -> popover berisi voice recognition
  with col_mic:
    with st.popover("🎤", help="Cari dengan suara", use_container_width=True):
      components.html(VOICE_HTML, height=140)

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
    col_img_thumb, col_img_info, col_img_btn = st.columns(
        [1, 6, 2], vertical_alignment="center"
    )
    with col_img_thumb:
      st.image(active_photo, width=65)
    with col_img_info:
      st.markdown("**Foto Acuan Terlampir**")
      st.caption("Menampilkan hasil berdasarkan kemiripan foto.")
    with col_img_btn:
      st.button(
          "❌ Hapus Foto",
          on_click=clear_photo,
          type="secondary",
          use_container_width=True,
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

  # Pencarian Gambar AI
  if active_photo:
    with st.spinner("Menganalisis kemiripan gambar..."):
      query_image = Image.open(active_photo)
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

  # Tampilan Data Output
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
