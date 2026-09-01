import streamlit as st
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import time

st.set_page_config(page_title="Katalog Inventory", page_icon="📦", layout="centered")

# --- Database Mock ---
DB = [
    {"id": 1, "nama": "Resistor 10k Ohm", "tipe": "Pasif", "stok": 150},
    {"id": 2, "nama": "Kapasitor 100uF", "tipe": "Pasif", "stok": 200},
    {"id": 3, "nama": "Arduino Uno R3", "tipe": "Mikrokontroler", "stok": 25},
    {"id": 4, "nama": "Sensor Suhu DHT11", "tipe": "Sensor", "stok": 50},
]

# State Management
if 'query_text' not in st.session_state:
    st.session_state.query_text = ""
if 'results' not in st.session_state:
    st.session_state.results = None

st.title("📦 Katalog Inventory")
st.write("Cari barang menggunakan teks, gambar, atau suara.")

# --- BAR INPUT MODEL GEMINI / CHATGPT ---
with st.container(border=True):
    col_menu, col_text, col_search = st.columns([1, 7, 2])

    # 1. TOMBOL MENU MELAYANG
    with col_menu:
        with st.popover("➕", help="Tambah Lampiran / Opsi"):
            st.markdown("### 📎 Lampiran & Fitur")
            
            # File Uploader Gambar
            uploaded_image = st.file_uploader("📷 Unggah Gambar Suku Cadang", type=["jpg", "jpeg", "png"])
            
            st.divider()
            
            # Perekam Suara dari Browser
            st.write("🎙️ **Pencarian Suara**")
            audio_record = mic_recorder(
                start_prompt="Klik untuk Rekam 🎙️",
                stop_prompt="Berhenti & Kirim ⏹️",
                key='recorder'
            )

    # 2. KOTAK TEKS UTAMA
    with col_text:
        query = st.text_input(
            "Cari...",
            value=st.session_state.query_text,
            placeholder="Ketik nama barang...",
            label_visibility="collapsed"
        )
        st.session_state.query_text = query

    # 3. TOMBOL CARI UTAMA
    with col_search:
        btn_cari = st.button("Cari 🔍", type="primary", use_container_width=True)

# Tentukan jika ada rekaman suara baru yang masuk
if audio_record is not None:
    audio_bytes = audio_record['bytes']
    r = sr.Recognizer()
    try:
        # Konversi bytes audio browser ke format speech recognition
        audio_file = BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="id-ID")
            st.session_state.query_text = text
            st.toast(f"Terekam: '{text}'", icon="🎙️")
    except Exception:
        st.error("Suara tidak terdeteksi atau tidak jelas. Coba lagi.")

# Tampilkan Indikator Gambar jika ada yang diunggah
if uploaded_image:
    st.info(f"📷 Gambar terlampir: **{uploaded_image.name}**")
    st.image(uploaded_image, width=120)

# --- LOGIKA PENCARIAN TERPADU ---
if btn_cari:
    with st.spinner("Mencari..."):
        time.sleep(0.5)
        if uploaded_image:
            st.success("Mencari berdasarkan gambar terlampir...")
            st.session_state.results = [DB[0], DB[1]]
        elif query:
            st.success(f"Mencari kata kunci: '{query}'")
            st.session_state.results = [i for i in DB if query.lower() in i['nama'].lower()]
        else:
            st.warning("Silakan masukkan teks, suara, atau unggah gambar terlebih dahulu.")

# --- TAMPILAN HASIL ---
if st.session_state.results is not None:
    st.subheader(f"Hasil ({len(st.session_state.results)})")
    for item in st.session_state.results:
        with st.container(border=True):
            st.write(f"**{item['nama']}** | Tipe: {item['tipe']} | Stok: {item['stok']}")
