"""
Pre-flight di avvio per utenti non tecnici.

Eseguito da edge_agent.main() prima di creare la MainWindow:
verifica i file essenziali, la chiave API (dialog al primo avvio),
i pesi DINOv2 (download con progresso e checksum al primo avvio) e il
warm-up del classificatore (saltato quando pesi e cache sono già validi).
Ogni problema è spiegato con un dialog in italiano.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

import app_paths
import env_key
import page_classifier
from config import AgentConfig
from page_classifier import (
    DINOV2_WEIGHTS_FILENAME,
    DINOV2_WEIGHTS_SHA256,
    DINOV2_WEIGHTS_URL,
)

# Fallback estremo se il template su disco non è leggibile:
# la fonte canonica è edge-agent/defaults/env.template.
ENV_TEMPLATE = (
    "# Configurazione Edge Agent\n"
    "LLM_PROVIDER=gemini\n"
    "LLM_MODEL=gemini-3.8-flash\n"
    "LLM_API_KEY=\n"
)

_KEY_ENV_VARS = ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


# ============================================================
# Helpers puri (testabili senza Qt)
# ============================================================

def _env_template_text() -> str:
    """Testo del template .env: file canonico in defaults/, fallback embedded."""
    try:
        tpl = app_paths.bundled_defaults_dir() / "env.template"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return ENV_TEMPLATE


def _has_api_key() -> bool:
    return any((os.getenv(var) or "").strip() for var in _KEY_ENV_VARS)


def _torch_hub_dir() -> Path:
    home = os.environ.get("TORCH_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "torch" / "hub"


def _weights_present() -> bool:
    return (_torch_hub_dir() / "checkpoints" / DINOV2_WEIGHTS_FILENAME).exists()


def _hub_repo_present() -> bool:
    """True se torch.hub ha già in cache il codice del repo DINOv2."""
    try:
        return any(_torch_hub_dir().glob("facebookresearch_dinov2_*"))
    except Exception:  # noqa: BLE001
        return False


def _recognition_ready() -> bool:
    """True se pesi, repo hub e cache prototipi sono già pronti: warm-up inutile."""
    return (
        _weights_present()
        and _hub_repo_present()
        and page_classifier.cache_is_valid(app_paths.templates_dir())
    )


# ============================================================
# Step di pre-flight (con UI)
# ============================================================

def _ensure_torch_home() -> None:
    """Da bundle, punta TORCH_HOME a una cache locale così la cartella resta portable."""
    if app_paths.is_frozen():
        cache = app_paths.torch_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("TORCH_HOME", str(cache))


def _ensure_files(parent: Optional[QtWidgets.QWidget]) -> bool:
    """Verifica file essenziali; ricrea config.ini e asset dal bundle se mancano."""
    base = app_paths.app_dir()
    try:
        probe = base / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception as exc:  # noqa: BLE001
        QtWidgets.QMessageBox.critical(
            parent, "Edge Agent",
            "La cartella dell'applicazione non è scrivibile:\n"
            f"{base}\n\nSpostala in una cartella normale (es. Desktop o Documenti).\n\n"
            f"Dettaglio: {exc}",
        )
        return False

    if str(base).startswith("\\\\"):
        QtWidgets.QMessageBox.warning(
            parent, "Edge Agent",
            "L'applicazione è su un percorso di rete: la chiave API salvata "
            "qui è leggibile da chiunque acceda alla cartella condivisa.",
        )

    cfg = app_paths.config_ini()
    if not cfg.exists():
        default_cfg = app_paths.bundled_defaults_dir() / "config.ini"
        if default_cfg.exists():
            shutil.copyfile(default_cfg, cfg)
        else:
            QtWidgets.QMessageBox.critical(
                parent, "Edge Agent",
                f"File di configurazione mancante e default non trovato:\n{cfg}",
            )
            return False

    tdir = app_paths.templates_dir()

    def _assets_ok() -> bool:
        return (
            (tdir / "prompts.json").exists()
            and tdir.exists()
            and any(
                p.suffix.lower() in {".png", ".jpg", ".jpeg"}
                for p in tdir.iterdir() if p.is_file()
            )
        )

    # Seed dal bundle: rende avviabile anche un bundle prodotto dal solo spec
    # (senza le copie top-level di build_exe.bat) e ripara cancellazioni accidentali.
    if not _assets_ok() and app_paths.is_frozen():
        bundled = app_paths.bundled_assets_dir()
        if bundled.exists():
            try:
                shutil.copytree(bundled, app_paths.app_dir() / "assets", dirs_exist_ok=True)
            except Exception:  # noqa: BLE001
                pass

    if not _assets_ok():
        QtWidgets.QMessageBox.critical(
            parent, "Edge Agent",
            "Cartella degli asset incompleta:\n"
            f"{tdir}\n\nLa cartella dell'applicazione è danneggiata: "
            "ripristina il pacchetto originale.",
        )
        return False

    # Catalogo prompt: stesso seed dal bundle degli asset, così una cancellazione
    # accidentale si ripara da sola. Non è bloccante come gli asset perché
    # prompt_store ripiega comunque sulla copia dentro il bundle; e non tocchiamo
    # una cartella già popolata, per non sovrascrivere i prompt editati a mano.
    pdir = app_paths.prompts_dir()
    if app_paths.is_frozen() and not (pdir.is_dir() and any(pdir.glob("*.json"))):
        bundled_prompts = app_paths.bundled_prompts_dir()
        if bundled_prompts.exists():
            try:
                shutil.copytree(bundled_prompts, pdir, dirs_exist_ok=True)
            except Exception:  # noqa: BLE001
                pass

    return True


def _load_local_env() -> None:
    """Carica il .env locale nel processo (best-effort, senza override)."""
    try:
        from dotenv import load_dotenv
        env_path = app_paths.env_file()
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except Exception:  # noqa: BLE001
        pass


def _ensure_api_key(parent: Optional[QtWidgets.QWidget]) -> bool:
    """Carica il .env locale; se la chiave manca la chiede con un dialog e la salva."""
    _load_local_env()
    env_path = app_paths.env_file()

    while not _has_api_key():
        raw, ok = QtWidgets.QInputDialog.getText(
            parent,
            "Configurazione iniziale",
            "Primo avvio: incolla la chiave API Gemini.\n"
            "Se non ce l'hai, chiedila a chi ti ha consegnato il programma.\n"
            "(viene salvata su questo computer e non verrà più richiesta):",
            QtWidgets.QLineEdit.EchoMode.Password,
        )
        if ok:
            key = env_key.sanitize_key(raw)
            if key is None:
                QtWidgets.QMessageBox.warning(
                    parent, "Edge Agent",
                    "La chiave inserita non è valida (vuota o con caratteri "
                    "non ammessi): riprova.",
                )
                continue
            try:
                env_key.write_key(env_path, key, _env_template_text())
                # Carica anche provider/modello del template appena scritto:
                # extraction li legge dall'ambiente del processo.
                _load_local_env()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.warning(
                    parent, "Edge Agent",
                    f"Impossibile salvare la chiave ({exc}): verrà richiesta di nuovo al prossimo avvio.",
                )
            os.environ["LLM_API_KEY"] = key
            break
        resp = QtWidgets.QMessageBox.question(
            parent,
            "Edge Agent",
            "Senza chiave API l'estrazione dei dati non può funzionare.\n"
            "Vuoi riprovare a inserirla?",
            QtWidgets.QMessageBox.StandardButton.Retry
            | QtWidgets.QMessageBox.StandardButton.Close,
            QtWidgets.QMessageBox.StandardButton.Retry,
        )
        if resp == QtWidgets.QMessageBox.StandardButton.Close:
            return False
    return True


class _WeightsDownloadWorker(QtCore.QThread):
    """Scarica i pesi DINOv2 nella cache torch, con progresso e verifica SHA-256."""

    progress = QtCore.pyqtSignal(int, int)
    finished_ok = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(str)

    def __init__(self, dest: Path, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.dest = dest
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        tmp = self.dest.with_suffix(".part")
        try:
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            sha = hashlib.sha256()
            with urllib.request.urlopen(DINOV2_WEIGHTS_URL, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                with tmp.open("wb") as f:
                    while True:
                        if self._cancelled:
                            raise InterruptedError("download annullato")
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
            # Integrità: blocca payload corrotti/sostituiti (proxy TLS, captive
            # portal salvato come .pth) prima che diventino la cache permanente.
            if sha.hexdigest() != DINOV2_WEIGHTS_SHA256:
                raise ValueError("checksum dei componenti non valido (download corrotto o intercettato)")
            tmp.replace(self.dest)
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            self.failed.emit(str(exc))


def _ensure_weights(parent: Optional[QtWidgets.QWidget]) -> bool:
    """
    Garantisce la presenza dei pesi DINOv2 (download con progresso al primo avvio).

    Ritorna False solo se l'utente sceglie di chiudere l'app; "continua senza"
    lascia i pesi assenti e il router degrada come da comportamento esistente.
    """
    while not _weights_present():
        dest = _torch_hub_dir() / "checkpoints" / DINOV2_WEIGHTS_FILENAME
        dlg = QtWidgets.QProgressDialog(
            "Primo avvio: scarico i componenti per il riconoscimento automatico (~85MB)...",
            "Annulla", 0, 100, parent,
        )
        dlg.setWindowTitle("Configurazione iniziale")
        dlg.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        worker = _WeightsDownloadWorker(dest)
        result: dict = {}
        loop = QtCore.QEventLoop()

        def on_progress(done: int, total: int) -> None:
            if total > 0:
                dlg.setMaximum(100)
                dlg.setValue(min(100, int(done * 100 / total)))

        def on_ok() -> None:
            result["ok"] = True
            loop.quit()

        def on_fail(msg: str) -> None:
            result["error"] = msg
            loop.quit()

        worker.progress.connect(on_progress)
        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        dlg.canceled.connect(worker.cancel)
        worker.start()
        loop.exec()
        worker.wait(5000)
        dlg.close()

        if result.get("ok"):
            break

        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("Edge Agent")
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setText(
            "Download dei componenti non riuscito.\n"
            f"Dettaglio: {result.get('error', 'sconosciuto')}\n\n"
            "Verifica la connessione a internet e riprova.\n"
            "Senza questi componenti il riconoscimento automatico delle schermate "
            "non funziona (lo scatto manuale resta disponibile)."
        )
        retry = box.addButton("Riprova", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("Continua senza", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        quit_btn = box.addButton("Esci", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is quit_btn:
            return False
        if clicked is skip:
            return True
        # Riprova: il while ricontrolla e riscarica
        _ = retry
    return True


def _warmup_classifier(parent: Optional[QtWidgets.QWidget]) -> bool:
    """
    Prepara il riconoscimento: scarica l'eventuale codice repo di torch.hub
    mancante, carica il modello e costruisce la cache dei prototipi.

    Ritorna False solo se l'utente sceglie Esci; Annulla e "Continua senza"
    lasciano proseguire l'avvio (il router degrada come da comportamento esistente).
    """
    while True:
        dlg = QtWidgets.QProgressDialog(
            "Preparo il riconoscimento automatico...", "Annulla", 0, 0, parent,
        )
        dlg.setWindowTitle("Configurazione iniziale")
        dlg.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)

        result: dict = {}
        cancelled: dict = {}
        loop = QtCore.QEventLoop()

        class _Warmup(QtCore.QThread):
            def run(self) -> None:  # noqa: D102
                try:
                    from page_classifier import (
                        BPERPagePrototypeClassifier,
                        DEFAULT_CROP_ROI,
                        DEFAULT_SIMILARITY_THRESHOLD,
                    )
                    clf = BPERPagePrototypeClassifier(
                        templates_dir=app_paths.templates_dir(),
                        crop_roi=DEFAULT_CROP_ROI,
                        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                        device="cpu",
                    )
                    info = clf.info()
                    if info.get("disabled"):
                        result["error"] = str(info.get("import_error") or "classificatore disabilitato")
                except Exception as exc:  # noqa: BLE001
                    result["error"] = str(exc)

        def on_cancel() -> None:
            cancelled["v"] = True
            loop.quit()

        worker = _Warmup()
        worker.finished.connect(loop.quit)
        dlg.canceled.connect(on_cancel)
        worker.start()
        loop.exec()
        dlg.close()

        if cancelled.get("v"):
            # Il thread di warm-up finisce in background; la cache che produce
            # verrà comunque riusata dal worker di cattura.
            return True

        worker.wait(5000)
        if not result.get("error"):
            return True

        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("Edge Agent")
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setText(
            "Preparazione del riconoscimento non riuscita.\n"
            f"Dettaglio: {result['error']}\n\n"
            "Se la rete aziendale blocca github.com questo passaggio non può "
            "completarsi: contatta l'assistenza.\n"
            "Senza il riconoscimento automatico lo scatto manuale resta disponibile."
        )
        box.addButton("Riprova", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("Continua senza", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        quit_btn = box.addButton("Esci", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is quit_btn:
            return False
        if clicked is skip:
            return True
        # Riprova: il while riesegue il warm-up


# ============================================================
# Entry point del pre-flight
# ============================================================

def run_preflight(parent: Optional[QtWidgets.QWidget] = None) -> Optional[AgentConfig]:
    """
    Esegue i controlli di ambiente e il setup di primo avvio.

    Ritorna la AgentConfig caricata se l'agent può partire, None se l'utente
    sceglie di uscire. In modalità smoke (EDGE_AGENT_SMOKE=1) salta i passaggi
    interattivi e i download così il processo termina sempre da solo.
    """
    _ensure_torch_home()
    if not _ensure_files(parent):
        return None

    config = AgentConfig(app_paths.config_ini())

    if os.getenv("EDGE_AGENT_SMOKE") == "1":
        _load_local_env()
        return config

    if not _ensure_api_key(parent):
        return None

    router_mode = (config.router_mode or "ml").lower()
    if router_mode in {"ml", "hybrid"}:
        if not _ensure_weights(parent):
            return None
        if not _recognition_ready():
            if not _warmup_classifier(parent):
                return None
    return config
