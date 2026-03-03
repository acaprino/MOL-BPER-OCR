"""Prompt definitions for VLM extraction passes."""

PROMPT = """
Sei un esperto di estrazione dati OCR da interfacce bancarie. Il tuo obiettivo è la MASSIMA PRECISIONE (zero errori di carattere).

REGOLE MANDATORIE:
1. IDENTIFICAZIONE PRATICA: I dati principali (NDG, Denominazione) si trovano al centro dell'interfaccia. IGNORA SEMPRE il nome dell'operatore in alto a destra (es. 'Crut Radu Ionut').
2. ANALISI TABELLE: Prima di estrarre, identifica mentalmente le colonne. Se una tabella ha 7 colonne, ogni oggetto JSON deve riflettere quelle 7 colonne. Non slittare i valori tra colonne diverse.
3. NDG e NUMERI: Estrai ogni cifra esattamente come appare. Non arrotondare, non troncare.
4. FEDELTÀ TESTUALE: 
   - Non correggere refusi.
   - NON sostituire termini tecnici o codici.
5. NUOVI CAMPI (Dati Anagrafici/Lavorativi): In alcune schermate potresti trovare dati su Professione, Nucleo Familiare, Reddito, Rating, Score CGS, ecc. Estrai tutto quello che vedi nei campi corrispondenti dello schema.
6. TOOLTIP: Cerca icone 'i', punti interrogativi o testi in popover/tooltip. 

STRUTTURA DATI:
- Soggetti: [NDG, DENOMINAZIONE, RUOLO]
- Fidi: [n° FIDO, Rapporto, Descrizione, Scadenza, Importo (€), Tipo Op.]
- Garanzie: [n° GAR, Descrizione, Fido, NDG, Denominazione, Imp. (€)/%, Tipo Op.]
- Altri Campi: Professione, Reddito, Nucleo Familiare, Rating, Score CGS.

IMPORTANTE: Restituisci SOLO un oggetto JSON valido conforme allo schema richiesto. Non includere spiegazioni o testo aggiuntivo fuori dal JSON.
""".strip()

ANCHOR_PROMPT = """
Estrai SOLO i seguenti campi dallo screenshot:
- ndg
- denominazione

Regole:
- NDG e Denominazione principali si trovano solitamente nell'intestazione della pratica al CENTRO dell'immagine.
- IGNORA i nomi e numeri in alto a destra (es. l'operatore 'Crut Radu Ionut' o il suo ID).
- Se non sei assolutamente certo, restituisci null.
- NDG deve essere una sequenza numerica ESATTA (non stimare).
- Non inventare mai valori.
- Imposta confidence >= 0.95 solo se il valore è chiaramente leggibile.

IMPORTANTE: Restituisci SOLO un oggetto JSON valido conforme allo schema richiesto. Non includere spiegazioni o testo aggiuntivo fuori dal JSON.
""".strip()

RETRY_PROMPT_HEADER = """
Sei un esperto di estrazione dati da testate di pratiche bancarie.
In questo ritaglio cerca i campi: NDG, Denominazione, Tipo, Stato, Fase, Evidenze.
Il campo 'Tipo' è spesso un codice breve come 'BMB' o 'BPI'. 
Presta MASSIMA attenzione ai Tooltip (icone 'i' o popover) vicino a questi campi. 
Se vedi un testo che sembra una descrizione lunga vicino a un campo breve, è probabilmente un tooltip.
Estrai i valori esattamente come appaiono.
""".strip()

RETRY_PROMPT_BODY = """
Sei un esperto di estrazione tabelle. In questo ritaglio sono presenti le tabelle 'Soggetti', 'Fidi' o 'Garanzie'.
Il tuo compito è estrarle con precisione chirurgica.

REGOLE TABELLE:
1. IDENTIFICA LE COLONNE: Guarda le intestazioni. Ogni colonna deve corrispondere esattamente al campo JSON.
2. ALLINEAMENTO: Assicurati che il valore della colonna 'NDG' non finisca in 'Denominazione'.
3. RIGHE MULTIPLE: Se una cella contiene testo su più righe (es. 'Rapporto'), uniscile con uno spazio.
4. COMPLETEZZA: Estrai tutte le righe, anche se sembrano simili.
5. GARANZIE: Fai attenzione alla colonna 'Imp. (€)/%'. Estrai il valore numerico completo.

Restituisci SOLO JSON.
""".strip()

RETRY_PROMPT_FOOTER = """
Sei un esperto di estrazione testi lunghi. In questo ritaglio cerca il campo 'Note della richiesta'.
Copia il testo PAROLA PER PAROLA. 
Non riassumere, non cambiare la punteggiatura, non aggiungere nulla.
Se il testo è troncato dal ritaglio, scrivi solo quello che vedi.

Restituisci SOLO JSON.
""".strip()

# Area mapping for retry prompts
FIELD_RETRY_PROMPTS = {
    "HEADER": RETRY_PROMPT_HEADER,
    "BODY": RETRY_PROMPT_BODY,
    "FOOTER": RETRY_PROMPT_FOOTER,
}
