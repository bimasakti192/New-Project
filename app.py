import re
from io import BytesIO

import pandas as pd
from PIL import Image
import requests
import streamlit as st

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


# --- CACHE DATABASE ---
@st.cache_data(ttl=300, show_spinner=False)
def load_database(url):
  df_raw = pd.read_csv(url)
  df_clean = df_raw.fillna("")
  return df_raw, df_clean


# --- CACHE UNDUH GAMBAR ---
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


def normalize_text(text):
  if pd.isna(text):
    return ""
  return re.sub(r"[\s\-]+", "", str(text)).lower()


# --- STATE MANAGEMENT ---
if "search_input" not in st.session_state:
  st.session_state["search_input"] = ""


def reset_search():
  st.session_state["search_input"] = ""


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

# Frame Bar Input Utama — gaya pill/rounded
with st.container(border=True, key="search_bar"):
  col_search, col_reset = st.columns([9, 0.7], vertical_alignment="center")

  # 1. KOLOM TEXT SEARCH GLOBAL
  with col_search:
    search_query = st.text_input(
        "Pencarian Global",
        key="search_input",
        placeholder="Ketik kata kunci pencarian...",
        label_visibility="collapsed",
    )

  # 2. TOMBOL RESET (ikon bulat aksen oranye)
  with col_reset:
    st.button(
        "✕",
        help="Hapus Pencarian",
        on_click=reset_search,
        use_container_width=True,
        key="btn_reset",
    )

active_text_query = search_query.strip()

st.markdown("---")

# --- PROSES PEMROSESAN HASIL PENCARIAN ---
if not active_text_query:
  st.subheader("Selamat datang!")
  st.info("Silakan ketik kata kunci pada kolom pencarian.")
else:
  norm_query = normalize_text(active_text_query)
  mask = (
      df_clean.astype(str)
      .apply(lambda row: row.apply(lambda val: norm_query in normalize_text(val)))
      .any(axis=1)
  )
  results_df = df_clean[mask]

  # Tampilan Data Output
  if results_df.empty:
    st.warning("Tidak ada data barang yang sesuai dengan pencarian Anda.")
  else:
    EXCLUDE_KEYWORDS = ["link", "foto", "drive", "url", "uom"]

    for index, row in results_df.iterrows():
      with st.container():
        col_foto, col_detail = st.columns([1, 3.5])

        with col_foto:
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
              uom_val = str(row.get(uom_col, "")).strip() if uom_col else ""
              st.markdown(f"**{col_clean} :** {val_display} {uom_val}".strip())
            else:
              st.markdown(f"**{col_clean} :** {val_display}")

      st.divider()
