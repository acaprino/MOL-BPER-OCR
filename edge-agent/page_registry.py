"""Single source of truth for BPER page identity: name, order, template, slug."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


def slugify(name: str) -> str:
    """Filesystem-safe key: 'Note da Richiesta' -> 'note_da_richiesta'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "pagina"


@dataclass(frozen=True)
class PageDef:
    """Canonical page definition (name doubles as display label and id)."""

    name: str
    order: int
    template: Optional[str]
    slug: str


class PageRegistry:
    """Loads prompts.json and resolves router labels (names or template stems)."""

    def __init__(self, pages: List[PageDef], catchall_name: Optional[str]) -> None:
        self.pages: List[PageDef] = sorted(pages, key=lambda p: p.order)
        self.catchall_name = catchall_name
        self._by_name: Dict[str, PageDef] = {p.name.lower(): p for p in self.pages}
        self._by_template: Dict[str, PageDef] = {
            p.template.lower(): p for p in self.pages if p.template
        }
        self._permissive: bool = False

    @classmethod
    def load(cls, prompts_path: Path) -> "PageRegistry":
        """Parse prompts.json; raises ValueError on missing/duplicate metadata."""
        spec = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
        pages: List[PageDef] = []
        catchall: Optional[str] = None
        for entry in spec.get("pages", []):
            name = (entry.get("name") or "").strip()
            if not name:
                raise ValueError("prompts.json: page entry without 'name'")
            if entry.get("catchall"):
                catchall = name
                continue
            order = entry.get("order")
            if not isinstance(order, int) or order < 1:
                raise ValueError(f"prompts.json: missing/invalid 'order' for '{name}'")
            template = (entry.get("template") or "").strip() or None
            pages.append(PageDef(name=name, order=order, template=template, slug=slugify(name)))
        _ensure_unique([p.name.lower() for p in pages], "name")
        _ensure_unique([p.order for p in pages], "order")
        _ensure_unique([p.template.lower() for p in pages if p.template], "template")
        return cls(pages, catchall)

    @classmethod
    def empty(cls) -> "PageRegistry":
        """Permissive fallback when prompts.json is unavailable/broken."""
        registry = cls([], None)
        registry._permissive = True
        return registry

    def resolve(self, label: Optional[str]) -> Optional[PageDef]:
        """Router label (page name or template stem) -> PageDef; None if catch-all/unknown."""
        if not label:
            return None
        key = label.strip().lower()
        if self.catchall_name and key == self.catchall_name.lower():
            return None
        found = self._by_name.get(key) or self._by_template.get(key)
        if found is not None:
            return found
        if self._permissive:
            return PageDef(name=label.strip(), order=0, template=None, slug=slugify(label))
        return None

    def acquirable(self, router_mode: str) -> List[PageDef]:
        """Pages reachable in the given router mode, in capture order."""
        if (router_mode or "ml").lower() == "ml":
            return [p for p in self.pages if p.template]
        return list(self.pages)

    def names(self, router_mode: str = "llm") -> List[str]:
        """Canonical names of acquirable pages (for UI combos)."""
        return [p.name for p in self.acquirable(router_mode)]


def _ensure_unique(values: List, what: str) -> None:
    seen = set()
    for value in values:
        if value in seen:
            raise ValueError(f"prompts.json: duplicate {what}: {value!r}")
        seen.add(value)
