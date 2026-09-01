import streamlit as st
import speech_recognition as sr
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

# Fungsi Rekam Suara (VN)
def process_voice():
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            st.toast("🎙️ Bicara sekarang...", icon="🎙️")
            audio = r.listen(source, timeout=3, phrase_time_limit=5)
            st.toast("⌛ Memproses suara...", icon="⌛")
        text = r.recognize_google(audio, language="id-ID")
        st.session_state.query_text = text
        st.rerun()
    except Exception as e:
        st.error("Gagal merekam suara. Pastikan mikrofon aktif.")

st.title("📦 Katalog Inventory")
st.write("Cari barang menggunakan teks, gambar, atau suara.")

# --- BAR INPUT MODEL GEMINI / CHATGPT ---
with st.container(border=True):
    col_menu, col_text, col_search = st.columns([1, 7, 2])

    # 1. TOMBOL MENU MELAYANG (Seperti di gambar Gemini)
    with col_menu:
        with st.popover("➕", help="Tambah Lampiran / Opsi"):
            st.markdown("### 📎 Lampiran & Fitur")
            
            # File Uploader Gambar (Sudah ada tombol 'X' bawaan Streamlit)
            uploaded_image = st.file_uploader("📷 Unggah Gambar Suku Cadang", type=["jpg", "jpeg", "png"])
            
            st.divider()
            
            # Tombol VN di dalam menu
            st.write("🎙️ **Pencarian Suara**")
            if st.button("Mulai Reakaman Suara", use_container_width=True):
                process_voice()

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

# Tampilkan Indikator Gambar jika ada yang diunggah
if uploaded_image:
    st.info(f"📷 Gambar terlampir: **{uploaded_image.name}** (Klik 'X' di menu ➕ untuk menghapus)")
    st.image(uploaded_image, width=120)

# --- LOGIKA PENCARIAN TERPADU ---
if btn_cari:
    with st.spinner("Mencari..."):
        time.sleep(0.5)
        if uploaded_image:
            st.success("Mencari berdasarkan gambar terlampir...")
            st.session_state.results = [DB[0], DB[1]] # Contoh hasil dummy
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
