import base64
import hashlib
import re
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
from PIL import Image

# ==============================================================================
# 🔗 KONFIGURASI
# ==============================================================================
DATABASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTcS0mSoo1HwqTihRlqwwhyxJSpVMW4WH15XM_rx2yLGfXCjbOn-SbEetgs5vRn8OWEFqO_ov-BgMwP/pub?output=csv"

# URL Web App hasil deploy Apps Script (yang berakhiran /exec)
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwYAY96yl2OROWECeItHTf7E_qA4jz8mWCpAre2nMseRrGE8zj7eZaTbNN6KB97itwC/exec"

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
# 🔐 LOGIN & ROLE
# ==============================================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_users():
    """Ambil daftar user dari secrets.toml -> [[users]] (username, password_hash, role)."""
    try:
        return st.secrets["users"]
    except Exception:
        return []


def check_login(username, password):
    users = get_users()
    entered_hash = hash_password(password)
    for u in users:
        if u.get("username") == username and u.get("password_hash") == entered_hash:
            return u.get("role", "staff")
    return None


def show_login_form():
    st.title("🔒 Login Katalog Komponen")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            role = check_login(username, password)
            if role:
                st.session_state["auth_username"] = username
                st.session_state["auth_role"] = role
                st.rerun()
            else:
                st.error("Username atau password salah.")


def show_logout_button():
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.get('auth_username')}**")
        st.caption(f"Role: {st.session_state.get('auth_role')}")
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("auth_username", None)
            st.session_state.pop("auth_role", None)
            st.rerun()


if "auth_username" not in st.session_state:
    show_login_form()
    st.stop()

show_logout_button()
IS_ADMIN = st.session_state.get("auth_role") == "admin"


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
if "edit_target" not in st.session_state:
    st.session_state["edit_target"] = None


def reset_search():
    st.session_state["search_input"] = ""


# ==============================================================================
# 🌐 KIRIM DATA + FOTO KE APPS SCRIPT
# ==============================================================================
def file_to_payload(uploaded_file):
    if uploaded_file is None:
        return None
    raw_bytes = uploaded_file.getvalue()
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return {
        "base64": b64,
        "mimeType": uploaded_file.type or "application/octet-stream",
        "fileName": uploaded_file.name,
    }


def call_apps_script(payload):
    resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def submit_new_item(lokasi_rak, kode_material, nama_barang, qty, uom, deskripsi, foto1, foto2):
    payload = {
        "action": "add",
        "lokasiRak": lokasi_rak,
        "kodeMaterial": kode_material,
        "namaBarang": nama_barang,
        "qty": qty,
        "uom": uom,
        "deskripsi": deskripsi,
        "foto1": file_to_payload(foto1),
        "foto2": file_to_payload(foto2),
    }
    return call_apps_script(payload)


def submit_update_item(
    kode_material_asli, lokasi_rak, kode_material, nama_barang, qty, uom, deskripsi,
    foto1, foto2, keep_foto1, keep_foto2,
):
    payload = {
        "action": "update",
        "kodeMaterialAsli": kode_material_asli,
        "lokasiRak": lokasi_rak,
        "kodeMaterial": kode_material,
        "namaBarang": nama_barang,
        "qty": qty,
        "uom": uom,
        "deskripsi": deskripsi,
        "foto1": file_to_payload(foto1),
        "foto2": file_to_payload(foto2),
        "keepFoto1": keep_foto1,
        "keepFoto2": keep_foto2,
    }
    return call_apps_script(payload)


# ==============================================================================
# 🧩 KOMPONEN: form edit inline untuk satu barang
# ==============================================================================
def render_edit_form(row, col_kode, col_lokasi, col_nama, col_qty, col_uom, col_deskripsi, photo_cols, unique_id):
    kode_val = str(row.get(col_kode, "")).strip()

    with st.form(f"form_edit_{unique_id}"):
        c1, c2 = st.columns(2)
        with c1:
            e_lokasi_rak = st.text_input(
                "Lokasi Rak *", value=str(row.get(col_lokasi, "")) if col_lokasi else "", key=f"e_lokasi_{unique_id}"
            )
            e_kode_material = st.text_input("Kode Material *", value=kode_val, key=f"e_kode_{unique_id}")
            e_nama_barang = st.text_input(
                "Nama Barang *", value=str(row.get(col_nama, "")) if col_nama else "", key=f"e_nama_{unique_id}"
            )
            qty_raw = str(row.get(col_qty, "0")) if col_qty else "0"
            try:
                qty_default = int(float(qty_raw)) if qty_raw.strip() else 0
            except ValueError:
                qty_default = 0
            e_qty = st.number_input("Qty", min_value=0, step=1, value=qty_default, key=f"e_qty_{unique_id}")
        with c2:
            e_uom = st.text_input(
                "UoM *", value=str(row.get(col_uom, "")) if col_uom else "", key=f"e_uom_{unique_id}"
            )
            e_deskripsi = st.text_area(
                "Deskripsi", value=str(row.get(col_deskripsi, "")) if col_deskripsi else "", key=f"e_desk_{unique_id}"
            )
            e_foto1 = st.file_uploader(
                "Ganti Foto 1 (kosongkan jika tidak diganti)",
                type=["png", "jpg", "jpeg"],
                key=f"e_foto1_{unique_id}",
            )
            e_foto2 = st.file_uploader(
                "Ganti Foto 2 (kosongkan jika tidak diganti)",
                type=["png", "jpg", "jpeg"],
                key=f"e_foto2_{unique_id}",
            )

        col_save, col_cancel = st.columns(2)
        with col_save:
            save_clicked = st.form_submit_button("💾 Simpan Perubahan", use_container_width=True)
        with col_cancel:
            cancel_clicked = st.form_submit_button("Batal", use_container_width=True)

        if cancel_clicked:
            st.session_state["edit_target"] = None
            st.rerun()

        if save_clicked:
            if not (e_lokasi_rak and e_kode_material and e_nama_barang and e_uom):
                st.error("Mohon lengkapi semua kolom bertanda *.")
            elif APPS_SCRIPT_URL.startswith("ISI_URL"):
                st.error("APPS_SCRIPT_URL belum diisi di kode.")
            else:
                with st.spinner("Menyimpan perubahan..."):
                    try:
                        result = submit_update_item(
                            kode_material_asli=kode_val,
                            lokasi_rak=e_lokasi_rak,
                            kode_material=e_kode_material,
                            nama_barang=e_nama_barang,
                            qty=e_qty,
                            uom=e_uom,
                            deskripsi=e_deskripsi,
                            foto1=e_foto1,
                            foto2=e_foto2,
                            keep_foto1=(e_foto1 is None),
                            keep_foto2=(e_foto2 is None),
                        )
                        if result.get("success"):
                            load_database.clear()
                            st.session_state["edit_target"] = None
                            st.success(result.get("message", "Data berhasil diperbarui!"))
                            st.rerun()
                        else:
                            st.error(result.get("message", "Gagal memperbarui data."))
                    except Exception as e:
                        st.error(f"Gagal memperbarui data: {e}")


# ==============================================================================
# 🗂️ TAB: PENCARIAN (dengan Edit inline khusus admin) | TAMBAH DATA (khusus admin)
# ==============================================================================
st.title("Katalog Komponen")

if IS_ADMIN:
    tab_cari, tab_tambah = st.tabs(["🔍 Cari Barang", "➕ Tambah Data Barang"])
else:
    tab_cari = st.container()
    tab_tambah = None

try:
    df_raw, df_clean = load_database(DATABASE_URL)
except Exception as e:
    st.error(f"Gagal memuat spreadsheet: {e}")
    st.stop()


def find_col(name_lower):
    for c in df_raw.columns:
        if c.strip().lower() == name_lower:
            return c
    return None


col_lokasi = find_col("lokasi rak")
col_kode = find_col("kode material")
col_nama = find_col("nama barang")
col_qty = find_col("qty")
col_uom = find_col("uom")
col_deskripsi = find_col("deskripsi")
photo_cols = [
    c for c in df_raw.columns if any(kw in c.lower() for kw in ["link", "foto", "drive", "url"])
]

# ------------------------------------------------------------------------------
# TAB PENCARIAN + EDIT INLINE (edit hanya untuk admin)
# ------------------------------------------------------------------------------
with tab_cari:
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
                kode_val = str(row.get(col_kode, "")).strip() if col_kode else str(index)

                with st.container():
                    if IS_ADMIN:
                        col_foto, col_detail, col_action = st.columns([1, 3, 0.8])
                    else:
                        col_foto, col_detail = st.columns([1, 3.5])
                        col_action = None

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

                    if IS_ADMIN and col_action is not None:
                        with col_action:
                            if col_kode is not None:
                                row_target = f"{kode_val}__{index}"
                                if st.button("✏️ Edit", key=f"btn_edit_{index}", use_container_width=True):
                                    st.session_state["edit_target"] = (
                                        None if st.session_state.get("edit_target") == row_target else row_target
                                    )
                                    st.rerun()

                    if IS_ADMIN and col_kode is not None and st.session_state.get("edit_target") == f"{kode_val}__{index}":
                        st.markdown("**Edit data barang ini:**")
                        row_raw = df_raw.loc[index] if index in df_raw.index else row
                        render_edit_form(
                            row_raw,
                            col_kode,
                            col_lokasi,
                            col_nama,
                            col_qty,
                            col_uom,
                            col_deskripsi,
                            photo_cols,
                            unique_id=f"{kode_val}__{index}",
                        )

                st.divider()

# ------------------------------------------------------------------------------
# TAB TAMBAH DATA BARU (khusus admin)
# ------------------------------------------------------------------------------
if IS_ADMIN and tab_tambah is not None:
    with tab_tambah:
        st.subheader("Tambah Data Barang Baru")
        st.caption(
            "Data akan dikirim ke Google Apps Script, yang otomatis upload foto ke Drive "
            "dan menulis baris baru ke spreadsheet."
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
                foto1 = st.file_uploader("Foto 1", type=["png", "jpg", "jpeg"], key="add_foto1")
                foto2 = st.file_uploader("Foto 2 (opsional)", type=["png", "jpg", "jpeg"], key="add_foto2")

            submitted = st.form_submit_button("💾 Simpan Data", use_container_width=True)

            if submitted:
                if not (lokasi_rak and kode_material and nama_barang and uom):
                    st.error("Mohon lengkapi semua kolom bertanda *.")
                elif APPS_SCRIPT_URL.startswith("ISI_URL"):
                    st.error("APPS_SCRIPT_URL belum diisi di kode.")
                else:
                    with st.spinner("Mengupload foto & menyimpan data..."):
                        try:
                            result = submit_new_item(
                                lokasi_rak, kode_material, nama_barang, qty, uom, deskripsi, foto1, foto2
                            )
                            if result.get("success"):
                                load_database.clear()
                                st.success(result.get("message", "Data berhasil disimpan!"))
                            else:
                                st.error(result.get("message", "Gagal menyimpan data."))
                        except Exception as e:
                            st.error(f"Gagal menyimpan data: {e}")
