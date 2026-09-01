import streamlit as st
import pandas as pd
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import requests
from io import BytesIO
from sklearn.metrics.pairwise import cosine_similarity
import re
import base64
import streamlit.components.v1 as components

# ==============================================================================
# 🔗 LINK CSV GOOGLE SHEETS
# ==============================================================================
DATABASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTcS0mSoo1HwqTihRlqwwhyxJSpVMW4WH15XM_rx2yLGfXCjbOn-SbEetgs5vRn8OWEFqO_ov-BgMwP/pub?output=csv"
# ==============================================================================

st.set_page_config(page_title="Katalog Komponen", layout="wide")

# --- 1. OPTIMASI CACHE MODEL & PREPROCESSING ---
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
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

# --- 2. OPTIMASI CACHE DATABASE (Hanya diunduh ulang tiap 5 menit) ---
@st.cache_data(ttl=300, show_spinner=False)
def load_database(url):
    df_raw = pd.read_csv(url)
    df_clean = df_raw.fillna('')
    return df_raw, df_clean

# --- 3. OPTIMASI CACHE UNDUH GAMBAR ---
def get_drive_direct_url(drive_url):
    file_id_match = re.search(r'(?:/d/|id=)([a-zA-Z0-9_-]+)', str(drive_url))
    if file_id_match:
        file_id = file_id_match.group(1)
        return f'https://lh3.googleusercontent.com/d/{file_id}'
    return drive_url

@st.cache_data(show_spinner=False)
def load_image_from_url(url):
    try:
        direct_url = get_drive_direct_url(url)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(direct_url, headers=headers, timeout=5)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
    except Exception:
        pass
    return None

def extract_features(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    img_t = transform(image).unsqueeze(0)
    with torch.no_grad():
        features = model(img_t)
    return features.squeeze().numpy()

# --- 4. OPTIMASI CACHE FITUR GAMBAR AI (Sangat mempercepat pencarian foto) ---
@st.cache_data(show_spinner=False)
def get_cached_image_features(url):
    img = load_image_from_url(url)
    if img:
        return extract_features(img)
    return None

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
    return re.sub(r'[\s\-]+', '', str(text)).lower()

# --- STATE RESET PENCARIAN ---
if "search_input" not in st.session_state:
    st.session_state["search_input"] = ""
if "voice_query" not in st.session_state:
    st.session_state["voice_query"] = ""

def reset_search():
    st.session_state["search_input"] = ""
    st.session_state["voice_query"] = ""

# --- BACA DATA DATABASE (DENGAN CACHE) ---
try:
    df_raw, df_clean = load_database(DATABASE_URL)
except Exception as e:
    st.error(f"Gagal memuat spreadsheet: {e}")
    st.stop()

photo_cols = [c for c in df_raw.columns if any(kw in c.lower() for kw in ['link', 'foto', 'drive', 'url'])]

# --- HEADER APLIKASI ---
st.title("Pencarian & Katalog Komponen")

col_search, col_filter, col_add, col_mic, col_reset = st.columns([3.5, 2, 0.8, 0.8, 0.8])

with col_search:
    search_query = st.text_input(
        "Pencarian Global", 
        key="search_input",
        placeholder="Ketik kata kunci pencarian...",
        label_visibility="collapsed"
    )

with col_filter:
    filter_column = st.selectbox(
        "Filter Kolom",
        options=["Semua Kolom"] + list(df_raw.columns),
        index=0,
        label_visibility="collapsed"
    )

uploaded_file = None
captured_image = None

with col_add:
    with st.popover("Tambah Foto", help="Upload Foto atau Buka Kamera"):
        tab_upload, tab_camera = st.tabs(["Upload", "Kamera"])
        with tab_upload:
            uploaded_file = st.file_uploader("Upload Foto", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
        with tab_camera:
            captured_image = st.camera_input("Ambil Foto", label_visibility="collapsed")

with col_mic:
    with st.popover("Suara", help="Cari via Voice Note (Auto Stop saat Diam)"):
        audio_html = """
        <div style="text-align: center; font-family: sans-serif;">
            <button id="recordBtn" style="padding: 8px 12px; background-color: #ef4444; color: white; border: none; border-radius: 6px; cursor: pointer;">
                Mulai Bicara
            </button>
            <p id="status" style="font-size: 11px; color: #666; margin-top: 6px;">Klik tombol untuk mulai</p>
        </div>

        <script>
        let mediaRecorder;
        let audioChunks = [];
        let audioContext;
        let analyser;
        let silenceStart;
        let isRecording = false;

        const recordBtn = document.getElementById('recordBtn');
        const status = document.getElementById('status');

        recordBtn.addEventListener('click', async () => {
            if (!isRecording) {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                audioContext = new AudioContext();
                analyser = audioContext.createAnalyser();
                const source = audioContext.createMediaStreamSource(stream);
                source.connect(analyser);

                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];

                mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                    const reader = new FileReader();
                    reader.readAsDataURL(audioBlob);
                    reader.onloadend = () => {
                        const base64Audio = reader.result.split(',')[1];
                        window.parent.postMessage({type: 'streamlit:setComponentValue', value: base64Audio}, '*');
                    };
                };

                mediaRecorder.start();
                isRecording = true;
                recordBtn.innerText = "Mendengarkan...";
                recordBtn.style.backgroundColor = "#22c55e";
                status.innerText = "Bicara sekarang, sistem auto-stop saat kamu diam.";

                silenceStart = Date.now();
                checkSilence();
            }
        });

        function checkSilence() {
            if (!isRecording) return;

            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            analyser.getByteFrequencyData(dataArray);

            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
            let average = sum / dataArray.length;

            if (average < 10) {
                if (Date.now() - silenceStart > 1500) {
                    mediaRecorder.stop();
                    isRecording = false;
                    recordBtn.innerText = "Selesai";
                    recordBtn.style.backgroundColor = "#3b82f6";
                    status.innerText = "Suara diproses...";
                    return;
                }
            } else {
                silenceStart = Date.now();
            }
            requestAnimationFrame(checkSilence);
        }
        </script>
        """
        voice_base64 = components.html(audio_html, height=85)

        if voice_base64:
            try:
                audio_bytes = base64.b64decode(voice_base64)
                res_text = transcribe_audio_bytes(audio_bytes)
                if res_text:
                    st.success(f"Terdengar: \"{res_text}\"")
                    st.session_state["voice_query"] = res_text
                else:
                    st.error("Suara kurang jelas, coba lagi.")
            except Exception:
                pass

with col_reset:
    st.button("Reset", help="Hapus Pencarian", on_click=reset_search)

active_photo = uploaded_file or captured_image
active_text_query = search_query.strip() if search_query.strip() else st.session_state["voice_query"].strip()

st.markdown("---")

if not active_text_query and not active_photo:
    st.subheader("Selamat datang!")
    st.info("Apa yang Anda cari hari ini? Silakan ketik kata kunci, masukkan foto, atau gunakan pencarian suara pada menu di atas.")
else:
    filtered_df = df_clean.copy()

    # --- PENCARIAN TEKS CEPAT ---
    if active_text_query:
        norm_query = normalize_text(active_text_query)
        
        if filter_column == "Semua Kolom":
            mask = filtered_df.astype(str).apply(
                lambda row: row.apply(lambda val: norm_query in normalize_text(val))
            ).any(axis=1)
        else:
            mask = filtered_df[filter_column].astype(str).apply(
                lambda val: norm_query in normalize_text(val)
            )
        filtered_df = filtered_df[mask]

    # --- PENGOLAHAN FOTO DENGAN CACHE AI ---
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
                    drive_url = str(row.get(p_col, '')).strip()
                    if drive_url:
                        # Menggunakan fitur bergambar yang tersimpan di cache
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

            filtered_df['Tingkat Kemiripan (%)'] = [round(s * 100, 2) if s >= 0 else 0 for s in similarities]
            filtered_df['Loaded_Images'] = loaded_images_dict

            filtered_df = filtered_df[filtered_df['Tingkat Kemiripan (%)'] >= 70]
            results_df = filtered_df.sort_values(by='Tingkat Kemiripan (%)', ascending=False)
    else:
        results_df = filtered_df

    # --- MENAMPILKAN DATA ---
    if results_df.empty:
        if active_photo:
            st.warning("Tidak ada barang yang cocok dengan tingkat kemiripan di atas 70%.")
        else:
            st.warning("Tidak ada data barang yang sesuai dengan pencarian Anda.")
    else:
        EXCLUDE_KEYWORDS = ['link', 'foto', 'drive', 'url', 'uom', 'loaded_images', 'tingkat kemiripan (%)']

        for index, row in results_df.iterrows():
            with st.container():
                col_foto, col_detail = st.columns([1, 3.5])

                with col_foto:
                    imgs = row.get('Loaded_Images', [])
                    if not active_photo:
                        imgs = []
                        for p_col in photo_cols:
                            drive_url = str(row.get(p_col, '')).strip()
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

                        val = str(row.get(col, '')).strip()
                        val_display = val if val else '-'

                        if col_lower == 'qty':
                            uom_col = next((c for c in df_raw.columns if c.strip().lower() == 'uom'), None)
                            uom_val = str(row.get(uom_col, '')).strip() if uom_col else ''
                            st.markdown(f"**{col_clean} :** {val_display} {uom_val}".strip())
                        else:
                            st.markdown(f"**{col_clean} :** {val_display}")

                    if 'Tingkat Kemiripan (%)' in row and row['Tingkat Kemiripan (%)'] > 0:
                        st.markdown(f"**Kemiripan Foto :** {row['Tingkat Kemiripan (%)']}%")

            st.divider()