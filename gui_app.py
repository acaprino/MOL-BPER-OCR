import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import os
import threading
import json
import pandas as pd
from extraction import (
    run_extraction_batch, 
    load_ground_truth, 
    eval_outputs, 
    build_debug_report, 
    export_to_csv, 
    FIELD_KEYS,
    PROVIDER_MODELS
)

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("AI Data Extractor - Multi-LLM Support")
        self.geometry("900x800")

        # Variabili
        self.api_key = tk.StringVar(value=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")))
        self.image_paths = []
        self.csv_path = tk.StringVar()
        self.provider_choice = tk.StringVar(value="openai")
        self.model_choice = tk.StringVar(value="gpt-4o")

        self.create_widgets()

    def create_widgets(self):
        # Notebook per i Tab
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tab_config = ttk.Frame(self.notebook)
        self.tab_results = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_config, text=" ⚙️ Configurazione & Log ")
        self.notebook.add(self.tab_results, text=" 📊 Risultati ")

        # --- TAB CONFIGURAZIONE & LOG ---
        main_frame = tk.Frame(self.tab_config, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # API Key
        tk.Label(main_frame, text="LLM API Key:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        tk.Entry(main_frame, textvariable=self.api_key, show="*", width=60).pack(pady=(0, 10), fill=tk.X)

        # Provider e Modello
        prov_mod_frame = tk.Frame(main_frame)
        prov_mod_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(prov_mod_frame, text="Provider:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky=tk.W)
        provider_menu = tk.OptionMenu(prov_mod_frame, self.provider_choice, *PROVIDER_MODELS.keys(), command=self.update_models)
        provider_menu.grid(row=1, column=0, padx=(0, 20), sticky=tk.W)

        tk.Label(prov_mod_frame, text="Modello:", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky=tk.W)
        self.model_menu = tk.OptionMenu(prov_mod_frame, self.model_choice, *PROVIDER_MODELS["openai"])
        self.model_menu.grid(row=1, column=1, sticky=tk.W)

        # Selezione Immagini
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        btn_images = tk.Button(btn_frame, text="📁 Seleziona Immagini", command=self.select_images, width=25)
        btn_images.pack(side=tk.LEFT, padx=5)
        self.lbl_images = tk.Label(btn_frame, text="0 immagini selezionate", fg="blue")
        self.lbl_images.pack(side=tk.LEFT)

        # Selezione CSV (opzionale)
        csv_frame = tk.Frame(main_frame)
        csv_frame.pack(fill=tk.X, pady=10)

        btn_csv = tk.Button(csv_frame, text="📊 Seleziona CSV Ground Truth", command=self.select_csv, width=25)
        btn_csv.pack(side=tk.LEFT, padx=5)
        self.lbl_csv_status = tk.Label(csv_frame, text="Nessun CSV", fg="gray")
        self.lbl_csv_status.pack(side=tk.LEFT)

        # Bottone Avvio
        self.btn_run = tk.Button(main_frame, text="🚀 AVVIA ESTRAZIONE DATI", command=self.start_extraction, 
                                bg="#0068c9", fg="white", font=("Arial", 12, "bold"), height=2)
        self.btn_run.pack(pady=20, fill=tk.X)

        # Area Log
        tk.Label(main_frame, text="Log di Elaborazione:", font=("Arial", 10)).pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(main_frame, height=12, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # --- TAB RISULTATI ---
        self.setup_results_tab()

    def update_models(self, provider):
        models = PROVIDER_MODELS.get(provider, [])
        self.model_choice.set(models[0] if models else "")
        menu = self.model_menu["menu"]
        menu.delete(0, "end")
        for m in models:
            menu.add_command(label=m, command=lambda value=m: self.model_choice.set(value))

    def setup_results_tab(self):
        paned = ttk.PanedWindow(self.tab_results, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        summary_frame = ttk.LabelFrame(paned, text=" Riepilogo ")
        self.summary_text = scrolledtext.ScrolledText(summary_frame, height=12, font=("Consolas", 10), bg="#f8f9fa")
        self.summary_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        paned.add(summary_frame, weight=1)

        details_frame = ttk.LabelFrame(paned, text=" Dati Estratti ")
        paned.add(details_frame, weight=2)

        tree_frame = ttk.Frame(details_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tree = ttk.Treeview(tree_frame, columns=("value", "conf"), show="tree headings")
        self.tree.heading("#0", text="Immagine / Campo")
        self.tree.heading("value", text="Valore Estratto")
        self.tree.heading("conf", text="Confidenza")
        
        self.tree.column("#0", width=250)
        self.tree.column("value", width=400)
        self.tree.column("conf", width=100, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def select_images(self):
        files = filedialog.askopenfilenames(title="Seleziona immagini", filetypes=[("Immagini", "*.png *.jpg *.jpeg")])
        if files:
            self.image_paths = list(files)
            self.lbl_images.config(text=f"{len(self.image_paths)} immagini selezionate", fg="green")

    def select_csv(self):
        file = filedialog.askopenfilename(title="Seleziona CSV", filetypes=[("CSV", "*.csv")])
        if file:
            self.csv_path.set(file)
            self.lbl_csv_status.config(text=os.path.basename(file), fg="green")

    def log(self, message):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)

    def start_extraction(self):
        if not self.api_key.get():
            messagebox.showerror("Errore", "Inserisci la API Key!")
            return
        if not self.image_paths:
            messagebox.showerror("Errore", "Seleziona almeno un'immagine!")
            return

        self.btn_run.config(state=tk.DISABLED)
        self.log_area.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self.run_process)
        thread.start()

    def run_process(self):
        try:
            self.log(f"Inizio elaborazione di {len(self.image_paths)} immagini...")
            
            def _on_complete(sid, res):
                self.log(f"Completato: {sid}")
            
            def _on_error(sid, err):
                self.log(f"Errore su {sid}: {err}")

            outputs = run_extraction_batch(
                self.image_paths,
                api_key=self.api_key.get(),
                provider_name=self.provider_choice.get(),
                model_main=self.model_choice.get(),
                parallel=True,
                max_workers=min(len(self.image_paths), 12),
                on_complete=_on_complete,
                on_error=_on_error
            )
            
            # Salvataggio risultati
            out_json = "poc_outputs_gui.json"
            out_csv = "poc_results_gui.csv"
            
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(outputs, f, indent=2, ensure_ascii=False)
            
            export_to_csv(outputs, out_csv)
            
            self.log(f"Risultati JSON salvati in {out_json}")
            self.log(f"Risultati CSV salvati in {out_csv}")

            # Confronto con GT
            metrics = None
            if self.csv_path.get():
                self.log("Caricamento Ground Truth...")
                gt = load_ground_truth(self.csv_path.get())
                metrics = eval_outputs(outputs, gt)
                self.log(f"Valutazione completata. Accuratezza (Filtered): {metrics.get('acc_filt', 0):.2%}")
                
                report_path = "poc_debug_gui.csv"
                build_debug_report(outputs, gt, report_path)
                self.log(f"Report di confronto salvato in {report_path}")

            self.log("PROCESSO COMPLETATO!")
            self.after(0, lambda: self.display_results(outputs, metrics))
            messagebox.showinfo("Successo", "Estrazione completata!")

        except Exception as e:
            self.log(f"ERRORE GENERALE: {str(e)}")
            messagebox.showerror("Errore", f"Si è verificato un errore: {str(e)}")
        finally:
            self.btn_run.config(state=tk.NORMAL)

    def display_results(self, outputs, metrics=None):
        self.summary_text.delete(1.0, tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)

        lines = []
        if metrics:
            lines.append("=== VALUTAZIONE ACCURATEZZA ===")
            lines.append(f"OVERALL (RAW):      {metrics.get('acc_raw', 0):.2%}")
            lines.append(f"OVERALL (FILTERED): {metrics.get('acc_filt', 0):.2%}")
            lines.append("")
            lines.append("Per-field Accuracy (FILTERED):")
            per_field = metrics.get('per_field_filt', {})
            for k, (c, t) in sorted(per_field.items()):
                lines.append(f"  {k:30s} {c:3d}/{t:3d} = {(c/t):.2%}")
            lines.append("\n" + "="*50 + "\n")

        lines.append("=== RIEPILOGO COSTI E STATUS ===")
        total_cost = 0.0
        total_tokens = 0
        total_calls = 0
        for scr, out in outputs.items():
            agg = out.get("_meta_agg", {})
            cost = float(agg.get("estimated_cost_usd", 0.0) or 0.0)
            toks = int(agg.get("total_tokens", 0) or 0)
            calls = int(agg.get("calls", 0) or 0)
            total_cost += cost
            total_tokens += toks
            total_calls += calls
            lines.append(f"  {scr:15s} | Chiamate: {calls:2d} | Tokens: {toks:5d} | Costo: ${cost:.4f} | Status: {out.get('_status')}")
        
        lines.append("-" * 70)
        lines.append(f" TOTALE | Chiamate: {total_calls} | Tokens: {total_tokens} | Costo: ${total_cost:.4f}")
        
        self.summary_text.insert(tk.END, "\n".join(lines))

        for scr, out in outputs.items():
            parent = self.tree.insert("", tk.END, text=scr, open=True)
            fields = out.get("fields", {})
            for f_key in FIELD_KEYS:
                f_data = fields.get(f_key)
                if f_data and isinstance(f_data, dict):
                    val = f_data.get("value")
                    conf = f_data.get("confidence", 0.0)
                    if val is not None and str(val).strip() != "":
                        self.tree.insert(parent, tk.END, text=f_key, values=(val, f"{conf:.2f}"))
            
            for tbl_name in ["soggetti", "fidi", "garanzie"]:
                tbl_data = out.get(tbl_name, [])
                if tbl_data:
                    tbl_parent = self.tree.insert(parent, tk.END, text=tbl_name.upper(), values=("", ""))
                    for i, row in enumerate(tbl_data):
                        row_parent = self.tree.insert(tbl_parent, tk.END, text=f"Elemento {i+1}", values=("", ""))
                        for k, v in row.items():
                            if v is not None and str(v).strip() != "" and k not in ("confidence", "evidence_text"):
                                self.tree.insert(row_parent, tk.END, text=k, values=(v, ""))
        
        self.notebook.select(self.tab_results)

if __name__ == "__main__":
    app = App()
    app.mainloop()
