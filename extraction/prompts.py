"""VLM prompt templates (Italian — domain requirement)."""

PROMPT = """
Sei un sistema di estrazione dati da screenshot di una web app (UI banca).
Devi estrarre SOLO i campi richiesti e restituire JSON conforme allo schema.

Regole:
- Se ci sono più soggetti (NDG 1..3, Denominazione 1..3, Ruolo 1..3), estrai TUTTE le righe della tabella in "soggetti" mantenendo l'ordine dall'alto verso il basso.

- Se un valore non è presente o non è leggibile: value = null e confidence <= 0.3.
- Trattare "N/D", "ND", "---", vuoto come null.
- Non inventare mai valori.
- Per ogni campo: includi evidence_text (breve estratto) e section (titolo sezione se visibile).
- Se ci sono più soggetti (NDG 1..4, Denominazione 1..4, Ruolo 1..4), popola l'array soggetti.

Campi (label/sinonimi):
- ndg: "NDG"
- denominazione: "DENOMINAZIONE", "Nominativo"
- tipo: "Tipo"
- evidenze: "Evidenze"
- filiale_relazione: "Filiale relazione"
- ultima_validazione: "Ultima validazione"
- professione_principale: "PROFESSIONE PRINCIPALE"
- numero_mensilita: "NUMERO MENSILITÀ", "MENSILITA"
- retribuzione_annua_netta: "RETRIBUZIONE ANNUA NETTA"
- tipo_contratto: "TIPO CONTRATTO"
- datore_lavoro_anagrafica: "ANAGRAFICA" (nella sezione/tab "DATORE DI LAVORO")
- dal: "DAL"
- rating_ufficiale: "RATING UFFICIALE"
- score_cgs: "SCORE CGS"
- nr_altri_componenti_nucleo_familiare: "NR. ALTRI COMPONENTI NUCLEO FAMILIARE"
- di_cui_percepiscono_reddito: "DI CUI PERCEPISCONO REDDITO"
- importo_totale_annuo_altri_componenti: "IMPORTO TOTALE ANNUO"
- note: "NOTE", "NOTE CONCLUSIVE"

Restituisci SOLO JSON.
""".strip()

ANCHOR_PROMPT = """
Estrai SOLO i seguenti campi dallo screenshot:
- ndg
- denominazione

Regole:
- Se non sei assolutamente certo, restituisci null.
- NDG deve essere una sequenza numerica ESATTA (non stimare).
- Non inventare mai valori.
- Imposta confidence >= 0.95 solo se il valore è chiaramente leggibile.

Restituisci SOLO JSON conforme allo schema.
""".strip()
