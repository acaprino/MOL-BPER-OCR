import streamlit as st
import os
import json
import pandas as pd

try:
    from extraction import (
        load_ground_truth,
        classify_field,
        dataset_mismatch_guard,
        run_extraction_batch,
        CSV_TO_SCHEMA,
    )
except ImportError:
    st.error("Errore: Impossibile importare le funzioni dal pacchetto extraction. Assicurati che sia presente.")

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="AI Data Extractor Pro",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STILE CSS PERSONALIZZATO (CATCHY) ---
st.markdown("""
    <style>
    .main {
        background-color: #f0f2f6;
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        background-color: #0068c9;
        color: white;
        font-weight: bold;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #004a91;
        border: 2px solid #004a91;
    }
    .upload-box {
        border: 2px dashed #0068c9;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        background-color: white;
    }
    .metric-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    .status-ok { color: #28a745; font-weight: bold; }
    .status-wrong { color: #dc3545; font-weight: bold; }
    .status-missing { color: #ffc107; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/data-extraction.png", width=80)
    st.title("Settings")
    
    api_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    model_choice = st.selectbox("Modello VLM", ["gpt-4o", "gpt-4o-mini"], index=0)
    
    st.divider()
    st.markdown("### Istruzioni")
    st.info("1. Carica uno o più screenshot\n2. Carica il file CSV Ground Truth (opzionale)\n3. Clicca su 'Avvia Estrazione'")

# --- HEADER ---
st.markdown("<h1 style='text-align: center; color: #0068c9;'>🔍 AI Data Extractor Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 1.2em;'>Trasforma i tuoi screenshot in dati strutturati con la potenza di GPT-4 Vision</p>", unsafe_allow_html=True)

# --- CARICAMENTO FILE ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🖼️ Screenshot")
    uploaded_images = st.file_uploader("Trascina qui le immagini (.png, .jpg)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

with col2:
    st.markdown("### 📊 Ground Truth (CSV)")
    uploaded_csv = st.file_uploader("Carica il file dati.csv per il confronto", type=["csv"])

# --- LOGICA DI ELABORAZIONE ---
if st.button("🚀 AVVIA ESTRAZIONE"):
    if not api_key:
        st.error("Inserisci una chiave API valida nella sidebar!")
    elif not uploaded_images:
        st.warning("Carica almeno un'immagine per procedere.")
    else:
        # Salvataggio temporaneo delle immagini caricate
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        image_paths = []
        for img_file in uploaded_images:
            path = os.path.join(temp_dir, img_file.name)
            with open(path, "wb") as f:
                f.write(img_file.getbuffer())
            image_paths.append(path)

        # Caricamento GT se presente
        gt_data = None
        if uploaded_csv:
            csv_path = os.path.join(temp_dir, "temp_gt.csv")
            with open(csv_path, "wb") as f:
                f.write(uploaded_csv.getbuffer())
            gt_data = load_ground_truth(csv_path)

        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        completed = [0]  # mutable counter for closure

        def _on_complete(sid, result):
            completed[0] += 1
            progress_bar.progress(completed[0] / len(image_paths))
            status_text.text(f"Completati {completed[0]}/{len(image_paths)}...")

        def _on_error(sid, exc):
            completed[0] += 1
            progress_bar.progress(completed[0] / len(image_paths))
            st.error(f"Errore su {sid}: {exc}")

        all_results = run_extraction_batch(
            image_paths,
            api_key=api_key,
            parallel=True,
            max_workers=5,
            on_complete=_on_complete,
            on_error=_on_error,
        )

        status_text.success("Estrazione completata!")
        
        # --- VISUALIZZAZIONE RISULTATI ---
        st.divider()
        st.header("📋 Risultati Estrazione")
        
        for sid, res in all_results.items():
            with st.expander(f"Dettagli: {sid}", expanded=True):
                c1, c2 = st.columns([1, 2])
                
                with c1:
                    # Mostra l'immagine
                    img_path = os.path.join(temp_dir, f"{sid}.png")
                    if os.path.exists(img_path):
                        st.image(img_path, use_column_width=True)
                    
                    # Metriche screen
                    meta = res.get("_meta_agg", {})
                    st.markdown(f"""
                        <div class="metric-card">
                            <p><b>Costo:</b> ${meta.get('estimated_cost_usd', 0):.4f}</p>
                            <p><b>Latenza:</b> {meta.get('latency_ms', 0)/1000:.2f}s</p>
                            <p><b>Tokens:</b> {meta.get('total_tokens', 0)}</p>
                        </div>
                    """, unsafe_allow_html=True)

                with c2:
                    # Tabella risultati
                    fields_data = []
                    fields = res.get("fields", {})
                    
                    # Confronto con GT se disponibile
                    gt_for_screen = gt_data.get(sid, {}) if gt_data else {}
                    mismatch = dataset_mismatch_guard(gt_for_screen, res) if gt_data else False
                    
                    for f_key, f_val in fields.items():
                        if not isinstance(f_val, dict):
                            continue
                        pred_v = f_val.get("value")
                        conf = f_val.get("confidence", 0)
                        
                        row = {
                            "Campo": f_key,
                            "Valore Predetto": pred_v,
                            "Confidenza": f"{conf:.2%}"
                        }
                        
                        if gt_data:
                            inv_map = {v: k for k, v in CSV_TO_SCHEMA.items()}
                            csv_label = inv_map.get(f_key, f_key)
                            gt_v = gt_for_screen.get(csv_label)
                            
                            row["Ground Truth"] = gt_v
                            status = classify_field(gt_v, pred_v, field_key=f_key)
                            row["Status"] = status
                            
                        fields_data.append(row)
                    
                    df_res = pd.DataFrame(fields_data)
                    st.table(df_res)
                    
                    if mismatch:
                        st.warning("⚠️ Possibile mismatch rilevato tra screenshot e Ground Truth!")

        # --- DOWNLOAD REPORT ---
        if all_results:
            json_str = json.dumps(all_results, indent=2)
            st.download_button(
                label="📥 Scarica JSON Completo",
                data=json_str,
                file_name="estrazione_risultati.json",
                mime="application/json"
            )

# --- FOOTER ---
st.divider()
st.markdown("<p style='text-align: center; color: gray;'>Powered by Streamlit & OpenAI</p>", unsafe_allow_html=True)
