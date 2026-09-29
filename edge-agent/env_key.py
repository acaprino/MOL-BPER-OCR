"""
Scrittura della chiave API nel .env dell'Edge Agent.

Unico punto che scrive LLM_API_KEY: lo usano il dialog di primo avvio
(bootstrap.py) e la build del pacchetto portable (build_exe.bat), che può
precompilare la chiave così il tester non deve sapere cosa sia.

Solo stdlib: la build lo esegue come script senza caricare Qt né torch.
Uso da build:  EDGE_AGENT_PACKAGE_KEY=<chiave> python env_key.py <percorso .env>
La chiave passa dall'ambiente, non dalla riga di comando, per non finire
nell'elenco dei processi.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

PACKAGE_KEY_VAR = "EDGE_AGENT_PACKAGE_KEY"
_TEMPLATE_FILE = Path(__file__).resolve().parent / "defaults" / "env.template"


def sanitize_key(raw: Optional[str]) -> Optional[str]:
    """
    Normalizza una chiave inserita: strip, tollera 'LLM_API_KEY=...' incollato
    per intero. Ritorna None se non è una chiave valida (vuota, multi-riga o con
    '=' residui, che nel .env diventerebbero una entry arbitraria).
    """
    key = (raw or "").strip()
    if key.upper().startswith("LLM_API_KEY="):
        key = key.split("=", 1)[1].strip()
    if not key or any(c in key for c in "\r\n="):
        return None
    return key


def write_key(env_path: Path, key: str, template_text: str) -> None:
    """
    Salva LLM_API_KEY nel .env indicato, preservando le altre righe.

    Se il file non esiste viene creato da template_text; se la riga esiste
    viene sostituita, altrimenti appesa.
    """
    if "\r" in key or "\n" in key:
        raise ValueError("la chiave non può contenere andate a capo")

    if env_path.exists():
        lines: List[str] = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = template_text.strip("\n").splitlines()

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("LLM_API_KEY="):
            lines[i] = f"LLM_API_KEY={key}"
            replaced = True
            break
    if not replaced:
        lines.append(f"LLM_API_KEY={key}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: List[str]) -> int:
    """Precompila la chiave nel .env del pacchetto; errore se manca o non è valida."""
    if len(argv) != 2:
        print(f"uso: {PACKAGE_KEY_VAR}=<chiave> python env_key.py <percorso .env>", file=sys.stderr)
        return 2
    key = sanitize_key(os.environ.get(PACKAGE_KEY_VAR))
    if key is None:
        print(
            f"[ERRORE] {PACKAGE_KEY_VAR} vuota o non valida (spazi, andate a capo o '='): "
            "pacchetto non creato.",
            file=sys.stderr,
        )
        return 1
    write_key(Path(argv[1]), key, _TEMPLATE_FILE.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
