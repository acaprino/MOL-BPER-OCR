# 0031 — Il pacchetto contiene il modello DINOv2

- Data: 2026-11-22
- Stato: Accettato

## Contesto

Con l'ADR 0030 i prototipi delle pagine arrivano pronti con l'app, ma il modello che produce gli
embedding, DINOv2 ViT-S/14, si scaricava ancora al primo avvio: il codice del repo da GitHub
(4 MB) e i pesi da `dl.fbaipublicfiles.com` (85 MB). Su una rete aziendale che blocca quei siti il
riconoscimento delle pagine non partiva mai. Il responsabile del progetto ha chiesto il 2026-11-22
che anche il modello faccia parte del pacchetto. Questa decisione supera la frase dell'ADR 0030
che lasciava i pesi al download.

## Decisione

- `build_exe.bat` lancia `tools/bundle_dinov2.py`, che mette nella `torch-cache` del pacchetto il
  repo al commit fissato in `DINOV2_HUB_REPO` e i pesi. Li copia dalla cache torch del PC di build,
  scarica solo ciò che manca, carica il modello una volta dal pacchetto e rifiuta pesi con uno
  SHA-256 diverso da `DINOV2_WEIGHTS_SHA256`: in quel caso la build si ferma.
- L'app non cambia: da pacchetto punta `TORCH_HOME` alla propria `torch-cache`, e con repo e pesi
  presenti `torch.hub` non va in rete e il pre-flight salta download e warm-up.
- Il repository non contiene i pesi: entrano solo nel pacchetto. Da sorgente il primo avvio li
  scarica come prima.

## Conseguenze e verifica

- Lo zip cresce di circa 89 MB.
- Con il proxy puntato su una porta chiusa, il modello si carica dalla `torch-cache` preparata dallo
  script.
- `tests/test_bundle_dinov2.py` verifica il nome della cartella del repo che `torch.hub` usa per il
  commit fissato, la copia dalla cache locale e il rifiuto di pesi con un altro SHA-256 o senza repo.
