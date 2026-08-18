from __future__ import annotations

"""
page_classifier.py

Classificatore ML per le pagine BPER basato su prototipi di embedding
(DINOv2 ViT-S/14 + cosine similarity).

Importantissimo:
    - Se torch/torchvision non sono disponibili o non si caricano (es. DLL mancanti
      su Windows), il classificatore NON fa crashare l'app:
        * si mette in stato "disabled"
        * classify() restituisce sempre (None, 0.0)
        * info() spiega perché è disabilitato

In questo modo:
    - l'applicazione gira anche senza motore ML
    - puoi sistemare l'ambiente Torch con calma
"""

import json
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ============================================================
# Costanti DINOv2 (unica definizione: bootstrap e router le importano da qui)
# ============================================================
# Ref pinnato a un commit: evita la chiamata di rete di torch.hub per risolvere
# il branch (bloccante dietro proxy) e congela il codice remoto a una revisione nota.
DINOV2_HUB_REPO = "facebookresearch/dinov2:7764ea0f912e53c92e82eb78a2a1631e92725fc8"
DINOV2_MODEL_NAME = "dinov2_vits14"
DINOV2_WEIGHTS_URL = "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
DINOV2_WEIGHTS_FILENAME = "dinov2_vits14_pretrain.pth"
DINOV2_WEIGHTS_SHA256 = "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"

# Tuning condiviso del classificatore BPER
#
# ROI sull'area applicativa, non sulla cromatura del browser. La ROI precedente
# (0.0, 0.12, 1.0, 0.30) inquadrava la barra delle tab: sui template stessi
# riconosceva 5 pagine su 9, e su un frame a schermo intero 1 su 9.
DEFAULT_CROP_ROI = (0.0, 0.20, 1.0, 0.98)

# Soglia sul punteggio *centrato* (vedi _refresh_proto_matrix). Sui coseni
# grezzi qualunque soglia era inutile: pagine diverse dello stesso applicativo
# condividono quasi tutti i pixel e stavano tutte fra 0.91 e 1.00, con margini
# di 0.003 fra la prima e la seconda. Togliendo la componente comune il margine
# medio sale a circa 0.11 e un rifiuto torna esprimibile.
DEFAULT_SIMILARITY_THRESHOLD = 0.35

# Lato del quadrato dato in pasto a DINOv2. Multiplo di 14 (patch size).
EMBED_SIDE = 224

# Sottocartelle del dataset che NON sono pagine (escluse dai prototipi)
_EXCLUDED_SUBDIRS = {"transitions"}

# Prefisso delle classi di SCARTO: prototipi che rappresentano cio' che NON e' una
# pagina del processo. Sono normali cartelle di prototipi, quindi la costruzione non
# cambia; cio' che cambia e' come classify() riporta una loro vittoria.
#
# Senza di esse il classificatore *deve* scegliere una pagina: misurato su fotogrammi
# reali, il 100% dei negativi veniva assegnato a una pagina, per costruzione e non per
# errore. Tre classi separate per tipo (BPER fuori processo, altro applicativo, schermate
# vuote) portano i falsi positivi dal 44% al 20% senza perdere accuratezza; un unico
# prototipo mediato si ferma al 44%, perche' media categorie che non si somigliano.
# Vedi docs/adr/0008.
REJECT_PREFIX = "SCARTO"


@dataclass
class Classification:
    """Esito completo di una classificazione.

    `label` resta None quando la risposta non e' una pagina, ma il perche' cambia la
    decisione di chi chiama:
      - `rejected_by` valorizzato: il frame ha perso contro un prototipo di scarto, cioe'
        e' stato *riconosciuto* come non-pagina. Interrogare l'LLM ha poco senso.
      - `rejected_by` None e score sotto soglia: semplicemente non riconosciuto. E' qui
        che un ripiego sull'LLM puo' pagare.

    `margin` e' la distanza dal secondo classificato: e' la grandezza su cui si decide
    se fidarsi della risposta locale, perche' l'accuratezza da sola non dice se una
    singola risposta e' separabile dalla successiva.
    """

    label: Optional[str]
    score: float
    margin: float
    runner_up: Optional[str]
    rejected_by: Optional[str]


def _scan_dataset_images(templates_dir: Path) -> Dict[str, List[Path]]:
    """
    Scansiona templates_dir e costruisce {page_type: [path_img, ...]}.

    Unisce immagini in root (page_type = stem del file) e sottocartelle
    (page_type = nome cartella), escludendo le sottocartelle non-pagina.
    """
    page_images: Dict[str, List[Path]] = {}

    root_imgs = sorted(
        p
        for p in templates_dir.glob("*")
        if p.is_file()
        and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
    )
    for img_path in root_imgs:
        page_type = img_path.stem
        if page_type not in page_images:
            page_images[page_type] = []
        page_images[page_type].append(img_path)

    subdirs = [
        d for d in templates_dir.iterdir()
        if d.is_dir() and d.name.lower() not in _EXCLUDED_SUBDIRS
    ]
    for subdir in sorted(subdirs):
        imgs = sorted(
            p
            for p in subdir.glob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        )
        if imgs:
            if subdir.name not in page_images:
                page_images[subdir.name] = []
            page_images[subdir.name].extend(imgs)

    if not page_images:
        raise RuntimeError(
            f"Nessuna immagine trovata in {templates_dir} "
            "(né in root, né in sottocartelle)."
        )

    return page_images


def embedding_geometry(crop_roi: Optional[Tuple[float, float, float, float]] = None,
                       reject_classes: int = 0) -> str:
    """Identita' del modo in cui un embedding viene prodotto.

    Fa parte della chiave di cache insieme all'hash del dataset. Prototipi e
    query devono essere immersi nello stesso modo: una cache indicizzata solo sul
    contenuto dei file continuerebbe a servire vettori costruiti con una ROI o un
    resize precedenti mentre le query usano i nuovi, e ogni punteggio diventa
    priva di senso senza che nulla lo segnali.

    `reject_classes` fa parte della chiave perche' aggiungere prototipi di scarto
    cambia il *comportamento*, non solo i dati: la stessa query che prima doveva
    per forza scegliere una pagina ora puo' essere rifiutata. L'hash del dataset
    cambierebbe comunque (le cartelle sono immagini in piu'), ma dichiararlo qui
    rende esplicito che le due configurazioni non sono intercambiabili.
    """
    roi = DEFAULT_CROP_ROI if crop_roi is None else crop_roi
    return (
        f"model={DINOV2_MODEL_NAME}"
        f"|roi={tuple(round(float(v), 4) for v in roi) if roi else None}"
        f"|resize={EMBED_SIDE}x{EMBED_SIDE}-squash"
        f"|score=centered-cosine"
        f"|reject={reject_classes}"
    )


def cache_is_valid(templates_dir: Path, cache_path: Optional[Path] = None) -> bool:
    """
    True se la cache prototipi esiste ed è coerente col dataset corrente.

    Non importa torch: usabile dal pre-flight per decidere se saltare il warm-up.
    """
    templates_dir = Path(templates_dir)
    cache = Path(cache_path) if cache_path else templates_dir / "bper_page_prototypes.json"
    if not cache.exists():
        return False
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        page_images = _scan_dataset_images(templates_dir)
        n_reject = sum(1 for k in page_images if k.startswith(REJECT_PREFIX))
        if data.get("geometry") != embedding_geometry(reject_classes=n_reject):
            return False
        return data.get("dataset_hash") == BPERPagePrototypeClassifier._compute_dataset_hash(page_images)
    except Exception:
        return False


@dataclass
class Prototype:
    """
    Rappresenta il prototipo di un page_type.

    Attributes:
        page_type: nome logico della pagina (es. "ricerca_pratica").
        embedding: vettore L2-normalizzato (shape [D]) su CPU (torch.Tensor o simile).
        count: numero di immagini usate per costruire il prototipo.
    """
    page_type: str
    embedding: Any
    count: int


class BPERPagePrototypeClassifier:
    """
    Classificatore pagina BPER basato su prototipi e DINOv2 ViT-S/14.

    Modalità operative:
        - NORMAL: torch/torchvision disponibili → estrazione feature reale
        - DISABLED: torch non disponibile / DLL mancanti → nessuna classificazione,
                    ma l'app continua a funzionare (classify() → (None, 0.0))

    Dataset supportato (due modalità):

      1) Modalità semplice:
         templates_dir/
            ricerca_pratica.png
            elenco_pratiche.png
            cruscotto_soggetti.png
            fidi_garanzie.png

      2) Modalità estesa:
         templates_dir/
            ricerca_pratica/
                img1.png
                img2.png
                ...
            elenco_pratiche/
                ...
            cruscotto_soggetti/
                ...
            fidi_garanzie/
                ...
    """

    def __init__(
            self,
            templates_dir: Path,
            *,
            cache_path: Optional[Path] = None,
            crop_roi: Optional[Tuple[float, float, float, float]] = None,
            similarity_threshold: float = 0.75,
            device: str = "cpu",
    ) -> None:
        """
        Args:
            templates_dir:
                Directory che contiene il dataset delle pagine.

            cache_path:
                File JSON per cache dei prototipi.
                Se None, usa templates_dir / "bper_page_prototypes.json".

            crop_roi:
                ROI relativa (x1, y1, x2, y2) in [0,1] da applicare prima del resize.
                Se None, usa l’immagine intera.

            similarity_threshold:
                Soglia minima di similarità coseno per accettare un match.

            device:
                "cpu" o "cuda". In scenari edge è tipicamente "cpu".
        """
        self.templates_dir = Path(templates_dir)
        if cache_path is None:
            cache_path = self.templates_dir / "bper_page_prototypes.json"
        self.cache_path = Path(cache_path)

        self.crop_roi = crop_roi
        self.similarity_threshold = float(similarity_threshold)
        self.requested_device = device

        # Stato di abilitazione: se torch non è disponibile, resta disabilitato
        self._disabled: bool = False
        self._import_error: Optional[str] = None

        # Riferimenti a torch / torchvision caricati lazy
        self._torch = None
        self._models = None
        self._T = None

        # Oggetti popolati solo se torch è disponibile
        self.device = None
        self.model = None
        self.embedding_dim: Optional[int] = None
        self.transform = None

        # Prototipi
        self.prototypes: Dict[str, Prototype] = {}
        self._proto_labels: List[str] = []
        self._proto_matrix = None  # torch.Tensor [N, D] su CPU
        self._proto_matrix_centered = None  # [N, D], centroide sottratto
        self._proto_mean = None  # [D], centroide dei prototipi

        # Provo a caricare torch in maniera difensiva
        self._lazy_init_torch()

        if self._disabled:
            # Se torch non è disponibile, non alziamo errori qui:
            # l'app continua a girare e classify() non riconoscerà nulla.
            return

        if not self.templates_dir.exists():
            # In modalità abilitata ha senso fallire subito se il dataset manca
            raise FileNotFoundError(f"templates_dir non trovato: {self.templates_dir}")

        # Inizializza modello / trasformazioni / prototipi
        self._init_feature_extractor_and_transform()
        self._load_or_build_prototypes()

    # -------------------------------------------------------------------------
    # Inizializzazione torch/torchvision
    # -------------------------------------------------------------------------

    def _lazy_init_torch(self) -> None:
        """
        Tenta l'import di torch/torchvision.

        Se fallisce (es. DLL mancanti su Windows), mette il classifier
        in stato DISABLED, senza far crashare l'applicazione.
        """
        try:
            import torch  # type: ignore[import]
            from torchvision import models, transforms as T  # type: ignore[import]
        except Exception as e:  # noqa: BLE001
            self._disabled = True
            self._import_error = (
                f"Impossibile importare torch/torchvision: {e}. "
                "Il classificatore ML è DISABILITATO. "
                "Verifica l'installazione di PyTorch e delle DLL di sistema."
            )
            # Non rilanciamo eccezione: l'app deve continuare.
            return

        # Se siamo qui, torch è disponibile
        self._torch = torch
        self._models = models
        self._T = T

        if self.requested_device == "cuda" and not torch.cuda.is_available():
            self.device = torch.device("cpu")
        else:
            self.device = torch.device(self.requested_device)

        self._disabled = False
        self._import_error = None

    # -------------------------------------------------------------------------
    # Inizializzazione modello / dataset
    # -------------------------------------------------------------------------

    def _init_feature_extractor_and_transform(self) -> None:
        """
        Carica DINOv2-Small (ViT-S/14) pre-addestrata e crea:
            - feature_extractor
            - embedding_dim
            - transform (resize + normalizzazione specifica DINOv2)
        """
        torch = self._torch
        T = self._T
        assert torch is not None and T is not None

        # Carichiamo DINOv2 Small tramite TorchHub
        # 'dinov2_vits14' è la versione Small, bilanciata per l'edge
        self.model = torch.hub.load(DINOV2_HUB_REPO, DINOV2_MODEL_NAME)

        # L'embedding dimension per ViT-S/14 è 384
        self.embedding_dim = 384

        self.model = self.model.to(self.device)
        self.model.eval()

        # Resize non conservativo delle proporzioni (squash), senza CenterCrop:
        # T.Resize(int) scala il lato CORTO, quindi su una ROI larga il
        # CenterCrop che seguiva teneva solo il quadrato centrale. Con la vecchia
        # ROI erano 224 px su 1555, cioe' il 14% della larghezza: al
        # classificatore arrivava un pezzo di barra delle tab e nessun contenuto
        # di pagina. Schiacciare l'intera ROI nel quadrato conserva tutto, e le
        # 9 pagine differiscono per la disposizione del contenuto, non per le
        # proporzioni.
        self.transform = T.Compose(
            [
                T.Resize(
                    (EMBED_SIDE, EMBED_SIDE),
                    interpolation=T.InterpolationMode.BICUBIC,
                ),
                T.ToTensor(),
                T.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def _list_dataset_images(self) -> Dict[str, List[Path]]:
        """Scansiona templates_dir; vedi _scan_dataset_images (funzione condivisa)."""
        return _scan_dataset_images(self.templates_dir)

    @staticmethod
    def _compute_dataset_hash(page_images: Dict[str, List[Path]]) -> str:
        """
        Hash stabile basato su nome file + digest del contenuto: sopravvive a
        clone, spostamenti della cartella ed estrazioni zip (path e mtime no).
        """
        h = hashlib.sha1()
        for page_type in sorted(page_images.keys()):
            for p in sorted(page_images[page_type]):
                try:
                    content_digest = hashlib.sha1(p.read_bytes()).hexdigest()
                except (FileNotFoundError, OSError):
                    continue
                h.update(page_type.encode("utf-8"))
                h.update(p.name.encode("utf-8"))
                h.update(content_digest.encode("utf-8"))
        return h.hexdigest()

    def _load_or_build_prototypes(self) -> None:
        """
        Tenta di caricare la cache dei prototipi, altrimenti li costruisce da zero.
        """
        if self._disabled:
            # In modalità DISABLED non costruiamo nulla.
            return

        torch = self._torch
        assert torch is not None

        page_images = self._list_dataset_images()
        current_hash = self._compute_dataset_hash(page_images)
        n_reject = sum(1 for k in page_images if k.startswith(REJECT_PREFIX))
        current_geometry = embedding_geometry(self.crop_roi, reject_classes=n_reject)

        if self.cache_path.exists():
            try:
                with self.cache_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if (
                    data.get("dataset_hash") == current_hash
                    and data.get("geometry") == current_geometry
                ):
                    self._load_prototypes_from_cache(data)
                    return
            except Exception:
                # Cache non valida, si ricostruisce
                pass

        self._build_prototypes(page_images)
        self._save_prototypes_to_cache(current_hash)

    def _build_prototypes(self, page_images: Dict[str, List[Path]]) -> None:
        """
        Costruisce i prototipi come media degli embedding normalizzati.
        """
        if self._disabled:
            return

        torch = self._torch
        assert torch is not None and self.embedding_dim is not None

        self.prototypes.clear()
        self._proto_labels = []
        self._proto_matrix = None

        with torch.no_grad():
            for page_type, paths in page_images.items():
                if not paths:
                    continue

                acc = torch.zeros(self.embedding_dim, dtype=torch.float32, device="cpu")
                count = 0

                for img_path in paths:
                    try:
                        from PIL import Image

                        img = Image.open(img_path).convert("RGB")
                    except Exception:
                        continue

                    emb = self._compute_embedding(img)
                    if emb is None:
                        continue

                    acc += emb
                    count += 1

                if count == 0:
                    continue

                proto = acc / count
                proto = torch.nn.functional.normalize(proto, p=2, dim=0)

                self.prototypes[page_type] = Prototype(
                    page_type=page_type,
                    embedding=proto.cpu(),
                    count=count,
                )

        self._refresh_proto_matrix()

    def _refresh_proto_matrix(self) -> None:
        """Aggiorna la matrice [N, D] di prototipi, il centroide e le etichette.

        Oltre alla matrice grezza calcola quella *centrata*: sottratto il
        centroide dei prototipi, ogni vettore conserva solo cio' che distingue
        quella pagina dalle altre. Sulle pagine di uno stesso applicativo la
        componente condivisa domina il coseno (similarita' fra pagine diverse fra
        0.91 e 1.00, margini di 0.003 fra prima e seconda): togliendola il
        vincitore non cambia ma il margine medio passa a circa 0.11, e la soglia
        di rifiuto torna a significare qualcosa.
        """
        if self._disabled:
            self._proto_labels = []
            self._proto_matrix = None
            self._proto_matrix_centered = None
            self._proto_mean = None
            return

        torch = self._torch
        assert torch is not None

        if not self.prototypes:
            self._proto_labels = []
            self._proto_matrix = None
            self._proto_matrix_centered = None
            self._proto_mean = None
            return

        labels = sorted(self.prototypes.keys())
        mats = [self.prototypes[pt].embedding.unsqueeze(0) for pt in labels]
        mat = torch.cat(mats, dim=0)  # [N, D]

        self._proto_labels = labels
        self._proto_matrix = mat

        # Con un solo prototipo il centroide coincide col prototipo e la
        # differenza e' il vettore nullo: si resta sul coseno grezzo.
        if len(labels) < 2:
            self._proto_mean = None
            self._proto_matrix_centered = None
            return

        self._proto_mean = mat.mean(dim=0)
        self._proto_matrix_centered = torch.nn.functional.normalize(
            mat - self._proto_mean, p=2, dim=1
        )

    def _save_prototypes_to_cache(self, dataset_hash: str) -> None:
        """Serializza i prototipi in JSON."""
        if self._disabled:
            return

        data = {
            "dataset_hash": dataset_hash,
            "geometry": embedding_geometry(
                self.crop_roi,
                reject_classes=sum(1 for k in self.prototypes if k.startswith(REJECT_PREFIX)),
            ),
            "created_at": int(time.time()),
            "prototypes": {},
        }

        for pt, proto in self.prototypes.items():
            data["prototypes"][pt] = {
                "embedding": proto.embedding.tolist(),
                "count": proto.count,
            }

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            # Problema di I/O non blocca il funzionamento runtime
            pass

    def _load_prototypes_from_cache(self, data: Dict) -> None:
        """Carica i prototipi da un dict JSON."""
        if self._disabled:
            return

        torch = self._torch
        assert torch is not None

        self.prototypes.clear()

        protos = data.get("prototypes", {}) or {}
        for pt, payload in protos.items():
            emb_list = payload.get("embedding")
            count = payload.get("count", 0)
            if not emb_list:
                continue

            emb = torch.tensor(emb_list, dtype=torch.float32)
            emb = torch.nn.functional.normalize(emb, p=2, dim=0)

            self.prototypes[pt] = Prototype(
                page_type=pt,
                embedding=emb.cpu(),
                count=int(count),
            )

        self._refresh_proto_matrix()

    # -------------------------------------------------------------------------
    # ROI & embedding
    # -------------------------------------------------------------------------

    def _apply_roi(self, image) -> any:
        """
        Applica la ROI (x1,y1,x2,y2) in [0,1] se configurata.

        Se crop_roi è None, restituisce l'immagine originale.
        """
        if self.crop_roi is None:
            return image

        x1_rel, y1_rel, x2_rel, y2_rel = self.crop_roi
        w, h = image.size

        x1 = max(0, min(w, int(x1_rel * w)))
        y1 = max(0, min(h, int(y1_rel * h)))
        x2 = max(0, min(w, int(x2_rel * w)))
        y2 = max(0, min(h, int(y2_rel * h)))

        if x2 <= x1 or y2 <= y1:
            return image

        return image.crop((x1, y1, x2, y2))

    def _compute_embedding(self, image) -> Optional[Any]:
        """
        Calcola embedding L2-normalizzato [D] (torch.Tensor su CPU).

        Restituisce None se il classificatore è disabilitato o in caso di errore.
        """
        if self._disabled:
            return None

        torch = self._torch
        assert torch is not None and self.transform is not None and self.device is not None

        try:
            img = image.convert("RGB")
            img = self._apply_roi(img)
            tensor = self.transform(img).unsqueeze(0).to(self.device)  # [1,3,H,W]
        except Exception:
            return None

        with torch.no_grad():
            # DINOv2 restituisce direttamente l'embedding del CLS token
            feat = self.model(tensor)  # [1, 384]
            feat = feat.view(-1)
            emb = torch.nn.functional.normalize(feat, p=2, dim=0)

        return emb.cpu()

    # -------------------------------------------------------------------------
    # API pubblica
    # -------------------------------------------------------------------------

    def classify_detailed(self, image) -> "Classification":
        """Classifica riportando anche margine e motivo di un eventuale rifiuto."""
        empty = Classification(None, 0.0, 0.0, None, None)
        if self._disabled or self._proto_matrix is None or not self._proto_labels:
            return empty

        emb = self._compute_embedding(image)
        if emb is None:
            return empty

        torch = self._torch
        assert torch is not None

        if self._proto_matrix_centered is not None and self._proto_mean is not None:
            proto_mat = self._proto_matrix_centered
            emb = torch.nn.functional.normalize(emb - self._proto_mean, p=2, dim=0)
        else:
            proto_mat = self._proto_matrix

        sims = torch.mv(proto_mat, emb)
        order = torch.argsort(sims, descending=True)
        best_idx = int(order[0].item())
        best_label = self._proto_labels[best_idx]
        best_score = float(sims[best_idx].item())

        runner_up = self._proto_labels[int(order[1].item())] if len(order) > 1 else None
        margin = best_score - float(sims[order[1]].item()) if len(order) > 1 else best_score

        if best_label.startswith(REJECT_PREFIX):
            return Classification(None, best_score, margin, runner_up, best_label)

        if best_score < self.similarity_threshold:
            return Classification(None, best_score, margin, runner_up, None)

        return Classification(best_label, best_score, margin, runner_up, None)

    def classify(self, image) -> Tuple[Optional[str], float]:
        """
        Classifica una pagina BPER.

        Returns:
            (label, score):
                - label: page_type oppure None
                - score: similarità coseno [0,1] del best_match (anche in caso di None)

        Conserva il contratto storico usato dai chiamanti esistenti; per margine e
        motivo del rifiuto usare classify_detailed().
        """
        result = self.classify_detailed(image)
        return result.label, result.score

    def info(self) -> Dict:
        """
        Informazioni diagnostiche utili per log / debug.
        """
        return {
            "templates_dir": str(self.templates_dir),
            "cache_path": str(self.cache_path),
            "similarity_threshold": self.similarity_threshold,
            "crop_roi": self.crop_roi,
            "device": str(self.device) if self.device is not None else None,
            "disabled": self._disabled,
            "import_error": self._import_error,
            "num_prototypes": len(self.prototypes),
            "prototype_counts": {
                pt: proto.count for pt, proto in self.prototypes.items()
            },
        }
