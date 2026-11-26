"""Per-practice coverage and operator directions for the BPER P1 screen variants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from page_registry import PageDef
from practice_consolidation import frame_ndg


@dataclass(frozen=True)
class _Location:
    """An application tab, navigator step and content tab from BPER P1."""

    tab: str = ""
    step: str = ""
    content_tab: str = ""


_LIST = _Location("Elenco Pratiche")
_SUBJECTS = _Location("PEF 2.0", "Elenco Soggetti")
_CREDIT = _Location("PEF 2.0", "Gestione Fidi e Garanzie", "Gestione Fidi e Garanzie")
_NOTES = _Location("PEF 2.0", "Gestione Fidi e Garanzie", "Note da Richiesta")


@dataclass(frozen=True)
class _View:
    location: _Location
    maneuver: str = ""
    optional: bool = False


# Template IDs identify the installed catalogue's variants independently of its display names.
_VIEWS = {
    "screen 1": _View(_LIST, "Porta la tabella a sinistra per vedere NDG e Denominazione."),
    "screen 2": _View(_LIST, "Scorri la tabella a destra fino alle colonne di assegnazione e data."),
    "screen 3": _View(_LIST, "Porta il puntatore sul valore di Evidenze per aprire il tooltip.", True),
    "screen 4": _View(_SUBJECTS),
    "screen 5": _View(_CREDIT),
    "screen 6": _View(_CREDIT, "Porta il puntatore sulla Descrizione nella tabella Fidi.", True),
    "screen 7": _View(_CREDIT, "Apri il tooltip sulla Descrizione della garanzia CONSAP, se presente.", True),
    "screen 8": _View(_CREDIT, "Apri il tooltip sulla Descrizione della garanzia ipotecaria, se presente.", True),
    "screen 9": _View(_NOTES),
}


def _view(page: PageDef) -> _View | None:
    return _VIEWS.get((page.template or "").lower())


def _distance(origin: _View | None, target: _View | None) -> int:
    if not origin or not target:
        return 4
    a, b = origin.location, target.location
    if a == b:
        return 0
    if a.tab != b.tab:
        return 3
    return 1 if a.step == b.step else 2


def _directions(origin: _View | None, target: PageDef) -> str:
    view = _view(target)
    if view is None:
        return f"Apri «{target.name}»."
    before = origin.location if origin else _Location()
    after = view.location
    instructions = []
    if before.tab != after.tab:
        instructions.append("Apri Elenco Pratiche." if after == _LIST else "Apri il dettaglio della pratica.")
    if after == _SUBJECTS and before.step != after.step:
        instructions.append("Nel Navigatore scegli Elenco Soggetti nella fase aperta.")
    elif after.step and before.step != after.step:
        instructions.append(f"Nel Navigatore scegli Istruttoria e poi {after.step}.")
    if after.content_tab and before.content_tab != after.content_tab:
        instructions.append(f"Seleziona la scheda {after.content_tab}.")
    if origin and origin.optional and not view.optional and before == after:
        instructions.append("Allontana il puntatore per chiudere il tooltip.")
    if view.maneuver:
        instructions.append(view.maneuver)
    return " ".join(instructions) or f"Apri «{target.name}»."


class CaptureNavigation:
    """Consume the extraction client's published prefix, once per completed frame."""

    def __init__(self, pages: Sequence[PageDef]) -> None:
        self.pages = tuple(pages)
        self.published = 0
        self.ndg: str | None = None
        self.identity_source = "unidentified"
        self._seen: dict[str | None, set[str]] = {}
        self._unavailable: dict[str, set[str]] = {}
        self._reopened_after: dict[tuple[str, str], int] = {}

    @property
    def captured(self) -> set[str]:
        return self._seen.get(self.ndg, set()).copy()

    def update(self, results: Sequence[dict], decisions: Sequence[dict] = ()) -> None:
        # On resume a correction may predate a subsequent successful recapture.
        # Its watermark includes frames that were accepted but still in flight.
        for event in decisions:
            sequence = event["sequence"]
            self._advance(results, min(len(results), sequence + 1))
            self.apply_decision(event["ndg"], event["page"], event["action"], sequence)
        self._advance(results, len(results))

    def _advance(self, results: Sequence[dict], stop: int) -> None:
        # get_results() releases a contiguous prefix in capture order. Even errors
        # occupy a slot. A signal payload alone does not have this property.
        for sequence in range(self.published, stop):
            result = results[sequence]
            if result.get("_status") == "ERROR":
                continue
            ndg = frame_ndg(result)
            if ndg is not None:
                self.ndg = ndg
                self.identity_source = "extracted"
            else:
                self.identity_source = "preceding" if self.ndg else "unidentified"
            seen = self._seen.setdefault(self.ndg, set())
            if ndg and None in self._seen:
                seen.update(self._seen.pop(None))
            page = result.get("_page_type")
            if page:
                if self.ndg:
                    key = (self.ndg, page)
                    if sequence <= self._reopened_after.get(key, -1):
                        continue
                    self._reopened_after.pop(key, None)
                seen.add(page)
                if self.ndg in self._unavailable:
                    self._unavailable[self.ndg].discard(page)
        self.published = stop

    def apply_decision(
        self, ndg: str, name: str, action: str, sequence: int,
        before_change: Callable[[], None] | None = None,
    ) -> None:
        if action == "reopen":
            self.reopen(ndg, name, sequence, before_change)
        elif action in ("skip", "restore"):
            self.set_available(ndg, name, action == "restore", before_change)

    def set_available(
        self, ndg: str, name: str, available: bool, before_change: Callable[[], None] | None = None,
    ) -> None:
        if ndg not in self._seen or name in self._seen[ndg]:
            return
        page = next((p for p in self.pages if p.name == name), None)
        view = _view(page) if page else None
        if not view or not view.optional:
            return
        currently_available = name not in self._unavailable.get(ndg, ())
        if currently_available == available:
            return
        if before_change is not None:
            before_change()
        if available:
            self._unavailable[ndg].remove(name)
        else:
            self._unavailable.setdefault(ndg, set()).add(name)

    def reopen(
        self, ndg: str, name: str, last_submitted: int, before_change: Callable[[], None] | None = None,
    ) -> None:
        if name not in self._seen.get(ndg, ()):
            return
        if before_change is not None:
            before_change()
        self._seen[ndg].remove(name)
        self._reopened_after[ndg, name] = last_submitted

    def snapshot(self, page_name: str | None, status: str, completed_sequence: int | None) -> dict[str, Any]:
        # The worker owns a single capture job. Its current visit, once accepted,
        # is the last capture. Older acknowledgements may only advance the prefix.
        if status == "captured" and completed_sequence != self.published - 1:
            status = "pending"
        state: dict[str, Any] = {
            "current_page": page_name, "status": status, "practice_ndg": None,
            "coverage_ndg": self.ndg,
            "identity_source": "unidentified", "next_page": None,
            "missing": [], "optional": [], "unavailable": [], "captured": [],
        }
        if status != "captured":
            state["action"] = {
                "recognizing": "Riconoscimento della schermata in corso.",
                "unrecognized": "Mostra Elenco Pratiche o una pagina della pratica aperta in PEF.",
                "observed": "Mantieni aperta la schermata fino all’acquisizione.",
                "pending": "Estrazione in corso. Puoi proseguire nella pratica.",
                "error": ("Mantieni aperta la schermata per riprovare l’acquisizione." if page_name
                          else "Verifica il monitor selezionato e la finestra da acquisire."),
            }[status]
            if self.ndg is None:
                return state
        else:
            state.update(practice_ndg=self.ndg, identity_source=self.identity_source)
        seen = self.captured
        skipped = self._unavailable.get(self.ndg, set())
        candidates = []
        current = next((p for p in self.pages if p.name == page_name), None)
        origin = _view(current) if current else None
        for page in self.pages:
            view = _view(page)
            if page.name in seen:
                state["captured"].append(page.name)
            elif page.name in skipped:
                state["unavailable"].append(page.name)
            else:
                optional = bool(view and view.optional)
                state["optional" if optional else "missing"].append(page.name)
                candidates.append((_distance(origin, view), optional, page.order, page))
        if status != "captured":
            return state
        if page_name and page_name not in seen:
            state["status"] = "review"
            if page_name not in skipped:
                state.update(next_page=page_name,
                             action="Controlla il nome della vista. Mostra la pagina corretta e acquisiscila di nuovo.")
                return state
        if candidates:
            target = min(candidates, key=lambda item: item[:3])[3]
            state.update(next_page=target.name, action=_directions(origin, target))
        elif self.pages:
            state["action"] = "Tutte le viste disponibili sono state acquisite. Puoi rivederle o cambiare pratica."
        else:
            state["action"] = "Puoi acquisire un’altra schermata della pratica."
        return state
