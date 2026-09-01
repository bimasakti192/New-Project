import streamlit as st
import speech_recognition as sr
from io import BytesIO
import time

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="Katalog Inventory Terpadu v2.0", page_icon="📦")

# --- Database Mock (Ganti dengan DB aslimu nanti) ---
DB = [
    {"id": 1, "nama": "Resistor 10k Ohm", "tipe": "Pasif", "stok": 150},
    {"id": 2, "nama": "Kapasitor 100uF", "tipe": "Pasif", "stok": 200},
    {"id": 3, "nama": "Arduino Uno R3", "tipe": "Mikrokontroler", "stok": 25},
    {"id": 4, "nama": "Sensor Suhu DHT11", "tipe": "Sensor", "stok": 50},
    {"id": 5, "nama": "Kabel Jumper Male-Female", "tipe": "Aksesoris", "stok": 500},
]

# --- Inisialisasi Session State (Sangat Penting) ---
# State untuk menyimpan hasil pencarian agar tidak hilang saat rerun
if 'results' not in st.session_state:
    st.session_state.results = None

# State untuk menyimpan teks dari VN agar bisa diisi ke text_input
if 'query_text' not in st.session_state:
    st.session_state.query_text = ""

# State untuk menyimpan gambar pencarian
if 'search_image_file' not in st.session_state:
    st.session_state.search_image_file = None


# --- Fungsi Logika Pencarian Terpadu ---
def perform_unified_search(img_file, text_query):
    """
    Fungsi tunggal untuk menjalankan pencarian.
    Prioritas: (1) Gambar > (2) Teks (Manual/VN)
    """
    # Beri indikasi pencarian sedang berjalan
    with st.spinner("📦 Menghubungkan ke gudang..."):
        time.sleep(1) # Simulasi delay jaringan (bisa dihapus)
        results = []

        if img_file:
            # --- Alur Prioritas 1: Pencarian Gambar ---
            st.success(f"🔍 Mencari suku cadang yang serupa dengan gambar: '{img_file.name}'")
            # LOGIKA PENCARIAN GAMBAR ASLI DIMASUKKAN DI SINI
            # (Untuk sekarang, tampilkan data dummy)
            results = [DB[0], DB[1]] # Contoh: Resistor dan Kapasitor

        elif text_query:
            # --- Alur Prioritas 2: Pencarian Teks/VN ---
            st.success(f"🔍 Mencari kata kunci: '{text_query}'")
            # LOGIKA PENCARIAN TEKS ASLI DIMASUKKAN DI SINI
            query_lower = text_query.lower()
            results = [item for item in DB if query_lower in item['nama'].lower()]

        else:
            # --- Tidak Ada Input ---
            st.warning("⚠️ Mohon ketik kata kunci, gunakan VN, atau unggah gambar terlebih dahulu.")
            st.session_state.results = None
            return

        # Simpan hasil ke session state
        st.session_state.results = results


# --- Fungsi Perbaikan Logika VN ---
def process_voice_search():
    """
    Fungsi untuk merekam suara, mentranskripsikannya ke teks,
    dan langsung mengisinya ke dalam kotak pencarian.
    """
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            st.toast("🎙️ Sedang merekam... Bicara sekarang!")
            # Beri sedikit waktu untuk mulai bicara
            time.sleep(0.5) 
            audio = r.listen(source, timeout=3, phrase_time_limit=5)
            st.toast("⌛ Selesai merekam. Sedang memproses...", icon="⌛")
            
        # Transkripsi suara ke teks menggunakan Google (Bahasa Indonesia)
        recognized_text = r.recognize_google(audio, language="id-ID")
        
        # Simpan teks hasil transkripsi ke session state agar diisi ke text_input
        st.session_state.query_text = recognized_text
        
        # Force rerun agar text_input memperbarui nilainya dengan teks VN
        st.experimental_rerun()

    except sr.WaitTimeoutError:
        st.error("⚠️ Tidak ada suara yang terdeteksi.")
    except sr.UnknownValueError:
        st.error("⚠️ Suara tidak jelas. Mohon ulangi.")
    except Exception as e:
        st.error(f"⚠️ Error tak terduga: {str(e)}")


# ==============================================================================
# --- TAMPILAN UTAMA APLIKASI (UI) ---
# ==============================================================================
st.title("📦 Katalog Inventory Terpadu")
st.markdown("Cari suku cadang di gudang dengan mudah.")

# --- KOTAK PENCARIAN TERPADU (Container) ---
with st.container(border=True):
    st.subheader("Pencarian Suku Cadang")

    # Tata letak menggunakan Kolom: Input Manual/VN | Gambar
    col_inputs, col_upload = st.columns([10, 3])

    with col_inputs:
        st.write("Cari lewat Nama/Kode Suku Cadang (Ketik atau Suara)")
        
        # Baris berisi Text Input dan Tombol VN
        col_text, col_vn = st.columns([12, 1])

        with col_text:
            # Input teks manual, nilainya dihubungkan ke session_state.query_text
            # label_visibility="collapsed" untuk menyembunyikan label bawaan
            manual_text = st.text_input(
                "Masukan kata kunci pencarian...",
                value=st.session_state.query_text,
                placeholder="Misal: 'Resistor 10k'",
                key="query_input",
                label_visibility="collapsed"
            )
            # Update state jika pengguna mengetik secara manual
            st.session_state.query_text = manual_text

        with col_vn:
            # Tombol VN dengan ikon mikrofon
            # Klik tombol ini akan memanggil fungsi process_voice_search()
            if st.button("🎙️", key="vn_btn", help="Gunakan VN (Pencarian Suara)"):
                process_voice_search()

    with col_upload:
        # File uploader untuk pencarian gambar
        # Tampilkan label di atas uploader
        st.write("Atau via Gambar:")
        uploaded_image = st.file_uploader(
            "Cari", # Label tidak tampil di UI modern
            type=["jpg", "png"],
            key="uploaded_file",
            label_visibility="collapsed"
        )
        
        # Simpan state gambar pencarian
        st.session_state.search_image_file = uploaded_image

        # Tampilkan pratinjau gambar jika ada
        # (Tampilan pratinjau di dalam uploader sudah cukup modern)
        if st.session_state.search_image_file:
            st.image(st.session_state.search_image_file, caption="Pencarian berbasis gambar", width=100)
            st.info("Pencarian akan didasarkan pada gambar ini.")

    st.write("---")
    
    # --- SATU-SATUNYA TOMBOL UTAMA UNTUK MENCARI ---
    # Klik tombol ini akan memanggil fungsi perform_unified_search()
    if st.button("Cari Sekarang!", type="primary", key="search_now_btn", use_container_width=True):
        final_query_text = manual_text if manual_text else st.session_state.query_text
        perform_unified_search(st.session_state.search_image_file, final_query_text)


# --- AREA HASIL PENCARIAN ---
if st.session_state.results is not None:
    st.write("---")
    st.subheader(f"Hasil Pencarian ({len(st.session_state.results)} ditemukan)")

    if st.session_state.results:
        # Loop dan tampilkan hasil dalam bentuk kartu sederhana
        for item in st.session_state.results:
            with st.container(border=True):
                col_item_icon, col_item_desc = st.columns([1, 6])
                with col_item_icon:
                    st.write("📦")
                with col_item_desc:
                    st.markdown(f"**Nama:** {item['nama']}")
                    st.markdown(f"**Tipe:** {item['tipe']} | **Stok:** {item['stok']}")
                    # Tampilkan link gambar jika ada (misal dari DB)
                    # st.image(item['img_url'], width=100) 
    else:
        st.warning("⚠️ Tidak ada suku cadang yang cocok dengan kriteria pencarian.")
