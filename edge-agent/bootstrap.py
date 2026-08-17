"""
Pre-flight di avvio per utenti non tecnici.

Eseguito da edge_agent.main() prima di creare la MainWindow:
verifica i file essenziali, la chiave API (dialog al primo avvio),
i pesi DINOv2 (download con progresso al primo avvio) e fa il warm-up
del classificatore. Ogni problema è spiegato con un dialog in italiano.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

import app_paths

# Pesi DINOv2 ViT-S/14 (stesso URL usato da torch.hub per 'dinov2_vits14')
DINOV2_WEIGHTS_URL = "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
DINOV2_WEIGHTS_FILENAME = "dinov2_vits14_pretrain.pth"

ENV_TEMPLATE = (
    "# Configurazione Edge Agent\n"
    "LLM_PROVIDER=gemini\n"
    "LLM_MODEL=gemini-3.6-flash\n"
    "LLM_API_KEY=\n"
)

_KEY_ENV_VARS = ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


# ============================================================
# Helpers puri (testabili senza Qt)
# ============================================================

def _save_env_key(env_path: Path, key: str) -> None:
    """
    Salva LLM_API_KEY nel .env indicato, preservando le altre righe.

    Se il file non esiste viene creato dal template; se la riga esiste
    viene sostituita, altrimenti appesa.
    """
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ENV_TEMPLATE.strip("\n").splitlines()

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("LLM_API_KEY="):
            lines[i] = f"LLM_API_KEY={key}"
            replaced = True
            break
    if not replaced:
        lines.append(f"LLM_API_KEY={key}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _has_api_key() -> bool:
    return any((os.getenv(var) or "").strip() for var in _KEY_ENV_VARS)


def _torch_hub_dir() -> Path:
    home = os.environ.get("TORCH_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "torch" / "hub"


def _weights_present() -> bool:
    return (_torch_hub_dir() / "checkpoints" / DINOV2_WEIGHTS_FILENAME).exists()


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
    """Verifica file essenziali; ricrea config.ini dal default se manca."""
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
    prompts = tdir / "prompts.json"
    has_pngs = tdir.exists() and any(
        p.suffix.lower() in {".png", ".jpg", ".jpeg"} for p in tdir.iterdir() if p.is_file()
    )
    if not prompts.exists() or not has_pngs:
        QtWidgets.QMessageBox.critical(
            parent, "Edge Agent",
            "Cartella degli asset incompleta:\n"
            f"{tdir}\n\nLa cartella dell'applicazione è danneggiata: "
            "ripristina il pacchetto originale.",
        )
        return False
    return True


def _ensure_api_key(parent: Optional[QtWidgets.QWidget]) -> bool:
    """Carica il .env locale; se la chiave manca la chiede con un dialog e la salva."""
    env_path = app_paths.env_file()
    try:
        from dotenv import load_dotenv
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except Exception:  # noqa: BLE001
        pass

    while not _has_api_key():
        key, ok = QtWidgets.QInputDialog.getText(
            parent,
            "Configurazione iniziale",
            "Primo avvio: incolla la chiave API Gemini\n"
            "(viene salvata su questo computer e non verrà più richiesta):",
        )
        if ok and key.strip():
            key = key.strip()
            try:
                _save_env_key(env_path, key)
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
    """Scarica i pesi DINOv2 nella cache torch con progresso (byte scaricati/totali)."""

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
                        done += len(chunk)
                        self.progress.emit(done, total)
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


def _warmup_classifier(parent: Optional[QtWidgets.QWidget]) -> None:
    """
    Inizializza una volta il classificatore DINO (best-effort, in thread).

    Scarica l'eventuale codice repo di torch.hub mancante e costruisce la
    cache dei prototipi, così la prima cattura è immediata. Un fallimento
    non blocca l'avvio: il router degrada come da comportamento esistente.
    """
    dlg = QtWidgets.QProgressDialog(
        "Preparo il riconoscimento automatico...", None, 0, 0, parent,
    )
    dlg.setWindowTitle("Configurazione iniziale")
    dlg.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)

    result: dict = {}
    loop = QtCore.QEventLoop()

    class _Warmup(QtCore.QThread):
        def run(self) -> None:  # noqa: D102
            try:
                from page_classifier import BPERPagePrototypeClassifier
                clf = BPERPagePrototypeClassifier(
                    templates_dir=app_paths.templates_dir(),
                    crop_roi=(0.0, 0.12, 1.0, 0.30),
                    similarity_threshold=0.70,
                    device="cpu",
                )
                info = clf.info()
                if info.get("disabled"):
                    result["error"] = str(info.get("import_error") or "classificatore disabilitato")
            except Exception as exc:  # noqa: BLE001
                result["error"] = str(exc)

    worker = _Warmup()
    worker.finished.connect(loop.quit)
    worker.start()
    loop.exec()
    worker.wait(5000)
    dlg.close()

    if result.get("error"):
        QtWidgets.QMessageBox.warning(
            parent, "Edge Agent",
            "Riconoscimento automatico non disponibile:\n"
            f"{result['error']}\n\nLo scatto manuale resta utilizzabile.",
        )


# ============================================================
# Entry point del pre-flight
# ============================================================

def run_preflight(parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """
    Esegue i controlli di ambiente e il setup di primo avvio.

    Ritorna False se l'utente sceglie di uscire; True se l'agent può partire.
    """
    _ensure_torch_home()
    if not _ensure_files(parent):
        return False
    if not _ensure_api_key(parent):
        return False

    # Pesi e warm-up servono solo se il router usa il classificatore ML
    try:
        from config import AgentConfig
        router_mode = (AgentConfig(app_paths.config_ini()).router_mode or "ml").lower()
    except Exception:  # noqa: BLE001
        router_mode = "ml"
    if router_mode in {"ml", "hybrid"}:
        if not _ensure_weights(parent):
            return False
        _warmup_classifier(parent)
    return True
