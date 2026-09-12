# Verifiche del coordinatore

## Suite esistente

Comando: `.venv/Scripts/python.exe -m pytest tests -o cache_dir=<run>/validation/pytest-cache`.

Risultato osservato: **153 passed, 3 warnings in 43.27s**, codice di uscita 0; nessun test fallito o saltato. Python 3.13.14, pytest 9.1.1, Windows. I tre warning segnalano xFormers non disponibile per SwiGLU, Attention e Block durante i test DINOv2 su CPU. Output integrale: [pytest.txt](pytest.txt).

L'esecuzione ha impostato `PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1` e `QT_QPA_PLATFORM=offscreen`; la cache pytest e i verbali sono nella directory del run. Queste sono evidenze di esecuzione raccolte dal coordinatore in applicazione della regola Testing & Validation di AGENTS.md, distinte dalle derivazioni statiche degli agenti.

## Limiti della verifica

La suite usa risposte simulate per il confine VLM e un classificatore DINOv2 reale nei test dedicati. Il successo dei test non misura l'accuratezza delle estrazioni su servizi LLM attivi, i loro costi reali o il funzionamento end-to-end delle interfacce desktop. Il CSV `mnt/data/dati.csv` non e' presente nel checkout; non e' stato eseguito il batch di valutazione con ground truth.

## Integrita' del perimetro

Lo snapshot iniziale registra commit `d28dac359cec` sul branch `develop`, con working tree modificato. Le cancellazioni di `.codebase-map/` e il file non tracciato `AGENTS.md` erano presenti prima dell'avvio degli agenti. Lo snapshot della skill esclude i file `.bat` e `.spec`: `launcher-baseline.json` ne conserva separatamente gli hash per la verifica finale.

## Riproduzione sintetica: ordine di consolidamento

Il coordinatore ha chiamato la funzione reale `edge-agent/practice_consolidation.py::consolidate` con tre risultati sintetici: pratica 111, nota senza NDG appartenente alla 111, pratica 222. Nell'ordine di cattura la nota viene attribuita alla 111; passando invece i risultati nell'ordine 111, 222, nota anonima, la stessa nota viene attribuita alla 222. Output: [consolidation-order.json](consolidation-order.json). Non e' una nuova suite di test e non altera i test esistenti.

La derivazione statica che rende rilevante il caso e' `edge-agent/local_extraction_client.py:175` (`LocalExtractionClient._process_frame`, append al termine dell'elaborazione), poi `edge-agent/ui/data_table_tab.py:195` (`DataTableTab._load_table`, consolidamento della lista restituita), infine `edge-agent/practice_consolidation.py:125` (`consolidate`, assegnazione a `last_key`). La riproduzione dimostra la sensibilita' all'ordine della funzione di consolidamento; non misura la frequenza di riordino nell'uso reale, ne' simula una sessione GUI completa.

## Verifica finale degli artefatti

I 14 rapporti (otto consolidati e sei di partizione) superano i controlli di esistenza, citazioni locali e limiti di riga, simboli qualificati rilevati, sezioni richieste, fence e chiusura dei subgraph Mermaid. Non sono state perse citazioni dai sei report di partizione; tutte le 152 firme pubbliche sono conservate. Sono stati verificati 69 collegamenti Markdown locali. Questa verifica strutturale non sostituisce una prova di rendering con ogni versione di Mermaid.

Il confronto con lo snapshot e il supplemento dei launcher conferma 121 file di codice e contesto invariati. Esiti: [artifact-validation.json](artifact-validation.json), [consolidation-validation.json](consolidation-validation.json). La pubblicazione verifica separatamente gli hash delle copie nel mirror: [publication.json](publication.json).
