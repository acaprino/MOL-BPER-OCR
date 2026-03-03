"""Prompt definitions for VLM extraction passes."""

PROMPT = """
Sei un esperto di estrazione dati OCR da interfacce bancarie. Il tuo obiettivo è la MASSIMA PRECISIONE (zero errori di carattere).

REGOLE MANDATORIE:
1. ANALISI TABELLE: Prima di estrarre, identifica mentalmente le colonne. Se una tabella ha 7 colonne, ogni oggetto JSON deve riflettere quelle 7 colonne. Non slittare i valori tra colonne diverse.
2. NDG e NUMERI: Estrai ogni cifra esattamente come appare. Non arrotondare, non troncare. Se vedi '11153238', scrivi '11153238'.
3. FEDELTÀ TESTUALE: 
   - Non correggere refusi (es. se vedi 'GIAMMARCO' e il sistema dice 'GIANMARCO', scrivi quello che vedi nell'immagine).
   - NON sostituire termini tecnici o codici (es. se vedi 'IPOSAP' non scrivere 'CONSAP', se vedi 'BMB' non scrivere 'BPI').
   - Per 'Note della richiesta': copia il testo PAROLA PER PAROLA. NON aggiungere bullet points (-), NON aggiungere spazi o tabulazioni extra, NON cambiare punteggiatura. Inizia esattamente con la prima parola visibile.
4. TOOLTIP: Cerca icone 'i', punti interrogativi o testi in popover/tooltip. Associa il contenuto al campo tooltip corrispondente. Spesso i tooltip appaiono quando il mouse passa sopra un valore (es. sopra 'BMB' o 'B').
5. NULL: Usa null solo se il campo è palesemente vuoto o non presente. Se è presente ma parzialmente coperto, estrai il leggibile.

STRUTTURA TABELLE:
- Soggetti: [NDG, DENOMINAZIONE, RUOLO]
- Fidi: [n° FIDO, Rapporto, Descrizione, Scadenza, Importo (€), Tipo Op.]
- Garanzie: [n° GAR, Descrizione, Fido, NDG, Denominazione, Imp. (€)/%, Tipo Op.] -> Attenzione: 'Imp. (€)/%' può contenere l'importo garantito, non confonderlo con la percentuale se presente.

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
