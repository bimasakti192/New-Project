import io
import re
from io import BytesIO

import gspread
import pandas as pd
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from PIL import Image

# ==============================================================================
# 🔗 KONFIGURASI
# ==============================================================================
DATABASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTcS0mSoo1HwqTihRlqwwhyxJSpVMW4WH15XM_rx2yLGfXCjbOn-SbEetgs5vRn8OWEFqO_ov-BgMwP/pub?output=csv"

# ID spreadsheet ASLI (bukan link publish). Ambil dari URL editor:
# https://docs.google.com/spreadsheets/d/ISI_ID_INI/edit
SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1SyeWtAjKAFyDs8oDVxKhiQluF45JjB_Se79PjmfrQxQ/edit?gid=0#gid=0"
SHEET_NAME = "Sheet1"  # ganti sesuai nama tab sheet kamu

# ID folder Drive tempat foto baru akan disimpan
DRIVE_FOLDER_ID = "https://drive.google.com/drive/folders/1UoMPOvUXmj2Ao9AWSE1f4-eQ7WgrTkZz?hl=ID"

# Urutan kolom di sheet — HARUS sama persis urutannya dengan kolom asli.
# Sesuaikan list ini kalau urutan/nama kolommu berbeda.
SHEET_COLUMNS = [
    "Lokasi Rak",
    "Kode Material",
    "Nama Barang",
    "Qty",
    "UoM",
    "Deskripsi",
    "Link Drive Foto",
    "Link Drive Foto",  # kolom foto kedua
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

st.set_page_config(page_title="Katalog Komponen", layout="wide")

# --- CSS: SEARCH BAR STYLE (PILL / ROUNDED SEPERTI CHAT BAR) --------------
st.markdown(
    """
    <style>
    .st-key-search_bar {
        border-radius: 28px !important;
        border: 1px solid #e5e5e5 !important;
        padding: 6px 14px !important;
        background: #ffffff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
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


# ==============================================================================
# 🔐 GOOGLE API HELPERS (Sheets & Drive lewat Service Account)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def get_google_credentials():
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )


@st.cache_resource(show_spinner=False)
def get_gspread_client():
    creds = get_google_credentials()
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_drive_service():
    creds = get_google_credentials()
    return build("drive", "v3", credentials=creds)


def upload_photo_to_drive(uploaded_file):
    """Upload 1 file foto ke folder Drive, set akses publik, kembalikan link view."""
    drive_service = get_drive_service()
    file_metadata = {"name": uploaded_file.name, "parents": [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.getvalue()),
        mimetype=uploaded_file.type or "application/octet-stream",
        resumable=False,
    )
    file = (
        drive_service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = file.get("id")
    drive_service.permissions().create(
        fileId=file_id, body={"role": "reader", "type": "anyone"}
    ).execute()
    return f"https://drive.google.com/file/d/{file_id}/view"


def append_row_to_sheet(row_values):
    gc = get_gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    ws.append_row(row_values, value_input_option="USER_ENTERED")


# --- CACHE DATABASE (untuk fitur pencarian, tetap pakai link publish) ---
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


# ==============================================================================
# 🗂️ TAB: PENCARIAN  |  TAMBAH DATA
# ==============================================================================
st.title("Katalog Komponen")

tab_cari, tab_tambah = st.tabs(["🔍 Cari Barang", "➕ Tambah Data Barang"])

# ------------------------------------------------------------------------------
# TAB 1: PENCARIAN (kode asli kamu, tidak diubah)
# ------------------------------------------------------------------------------
with tab_cari:
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

    with st.container(border=True, key="search_bar"):
        col_search, col_reset = st.columns([9, 0.7], vertical_alignment="center")

        with col_search:
            search_query = st.text_input(
                "Pencarian Global",
                key="search_input",
                placeholder="Ketik kata kunci pencarian...",
                label_visibility="collapsed",
            )

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

# ------------------------------------------------------------------------------
# TAB 2: TAMBAH DATA BARU (fitur baru)
# ------------------------------------------------------------------------------
with tab_tambah:
    st.subheader("Tambah Data Barang Baru")
    st.caption(
        "Data akan langsung ditulis ke spreadsheet. Foto otomatis diupload ke Google Drive "
        "dan link-nya dimasukkan ke kolom yang sesuai."
    )

    with st.form("form_tambah_barang", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            lokasi_rak = st.text_input("Lokasi Rak *")
            kode_material = st.text_input("Kode Material *")
            nama_barang = st.text_input("Nama Barang *")
            qty = st.number_input("Qty", min_value=0, step=1)
        with c2:
            uom = st.text_input("UoM (PCS, BOX, dll) *")
            deskripsi = st.text_area("Deskripsi")
            foto1 = st.file_uploader("Foto 1", type=["png", "jpg", "jpeg"], key="foto1")
            foto2 = st.file_uploader("Foto 2 (opsional)", type=["png", "jpg", "jpeg"], key="foto2")

        submitted = st.form_submit_button("💾 Simpan Data", use_container_width=True)

        if submitted:
            if not (lokasi_rak and kode_material and nama_barang and uom):
                st.error("Mohon lengkapi semua kolom bertanda *.")
            else:
                with st.spinner("Mengupload foto & menyimpan data..."):
                    try:
                        link1 = upload_photo_to_drive(foto1) if foto1 is not None else ""
                        link2 = upload_photo_to_drive(foto2) if foto2 is not None else ""

                        append_row_to_sheet(
                            [
                                lokasi_rak,
                                kode_material,
                                nama_barang,
                                qty,
                                uom,
                                deskripsi,
                                link1,
                                link2,
                            ]
                        )

                        load_database.clear()  # biar tab pencarian langsung lihat data baru
                        st.success("Data berhasil disimpan!")
                    except Exception as e:
                        st.error(f"Gagal menyimpan data: {e}")
