/* The BStore result list keeps the identification columns pinned for part of its travel. */
(() => {
  "use strict";

  // A table with rows sizes every column to its content: the widest of label (with its icons) and values, plus the
  // padding (list.css). The same column is as wide at 1164, 1283 and 1608 CSS px: nothing stretches (spec 19.3).
  const columns = ["", "ABI", "NDG", "Denom.", "N°", "Tipo", "Importo €", "Stato", "Fase", "Creazione",
    "Data Ass./Del.", "Assegnata", "Dest.", "Delib.", "D.R.", "Area", "Filiale", "Evidenze", ""];
  const filters = new Set(["ABI", "Tipo", "Stato", "Fase", "D.R.", "Area", "Filiale", "Evidenze"]);
  // Denom. has two regimes (spec 19.3). A name that fits shows whole and sizes the column; a longer one is cut with
  // an ellipsis in a box as wide as the label, and the column keeps the label's width. The video shows whole names up
  // to 18 characters (170 CSS px of text at 100%, 123 px here) and cut ones from 33 characters (~300 px, 217 here):
  // any limit in between fits it, and whether the real page counts characters or pixels is not visible. 127 px keeps
  // the cut of every catalogue name where the truth already puts it (bper_simulator_truth.list_name_fits, which reads
  // this limit from list_font_metrics.json: measure_list_font.cjs takes it from BperList.nameLimit).
  // shortcut: 127 px chosen inside the 123-217 px the video allows (pixels or characters unknown), replace when a frame shows a name of 19-32 characters in the list
  const nameLimit = 127;
  const nameFont = '12px "Segoe UI", Arial, sans-serif'; // the row font of list.css
  // Once scrolled, the identity columns stick a little left of where they start: NDG 4.75 and Denom. 12.4 CSS px at
  // 100%, ABI not at all (spec 19.4: 5 and 13 video px in each of MOL 04 00:46, MOL 06 37:45, MOL 10 00:56, MOL 11 01:09
  // against 18:10; reference screens 1-2, scrolled at 110%, put the two labels as close together). How the real table
  // gets there is not visible (sticky offsets fixed for narrower columns would do it): these are the measured shifts,
  // in reference px.
  // shortcut: NDG 4.75 / Denom. 12.4 CSS px measured on 4 frames, mechanism unknown, replace when a frame shows how the real page sticks them
  const settled = [0, 0, 3.4, 9.0];
  // An APP or ABB row has a checkbox in the first cell; with it NDG and every later column move 30 CSS px right while
  // ABI keeps its place (MOL 05 51:25, MOL 06 11:23). The calibration fold disagrees (APP 4 of 4 rows, ABB 0 of 6, LAV
  // 1 of 2), but APP-only does not fit it either: it frees 52126316's row and makes 52130861's too narrow. Not state-driven.
  // shortcut: APP and ABB as the video frames read them, cause unknown, replace when a frame shows what decides the checkbox
  const selectable = new Set(["APP", "ABB"]);
  // The Evidenze cell's other marks, in the real cell's order around the codes: clip, note bubble, (B, BC or BM),
  // diamond, (V), loop arrow, pink P. Their meaning is unknown, so only an invented (sintetica) practice gets them, each
  // picked from its key with the share of the 12 calibration rows showing it; archive practices and the reference show
  // their codes alone. bper_simulator_truth.evidence_slots counts them the same way for the end-of-scroll geometry.
  // shortcut: marks drawn from the shares of 12 rows (clip 11, note 4, diamond 3, loop 6, P 6), replace when a practice's data says which it has
  const markShare = { clip: 11 / 12, note: 4 / 12, diamond: 3 / 12, loop: 6 / 12, p: 6 / 12 };
  // FNV-1a of "<key>|<mark>" as a fraction of 2^32.
  function draw(text) {
    let hash = 0x811c9dc5;
    for (const c of text) hash = Math.imul(hash ^ c.codePointAt(0), 0x01000193) >>> 0;
    return hash / 2 ** 32;
  }
  // At most six marks in a row, the most a calibration row shows: past that the rarest other marks are left out.
  const maxMarks = 6;
  function otherMarks(p, codes) {
    if (p.role !== "sintetica") return new Set();
    const drawn = Object.keys(markShare).filter((mark) => draw(p.key + "|" + mark) < markShare[mark]);
    return new Set(drawn.sort((a, b) => markShare[b] - markShare[a]).slice(0, Math.max(0, maxMarks - codes)));
  }
  // The empty BStore table has no "N°" column. Its actions column is not pinned, so right of the
  // pinned Evidenze header the scrolling header row shows through: the tail of "Data Ass./Del.".
  // Without rows the widths are those measured: ABI, NDG and Denom. do not follow the label + padding rule there
  // (video 18:10: 15, 57 and 35 CSS px between their labels where the populated table has 24-28).
  // shortcut: empty-table widths measured on reference screens 1-3 and video 18:10, rule unknown, replace when a frame shows why ABI, NDG and Denom. differ there
  const lowerColumns = [
    ["", 36], ["ABI", 65], ["NDG", 83], ["Denom.", 83], ["Tipo", 75], ["Importo €", 88], ["Stato", 80],
    ["Fase", 76], ["Creazione", 91], ["Data Ass./Del.", 111], ["Assegnata", 88], ["Dest.", 61],
    ["Delib.", 65], ["D.R.", 74], ["Area", 78], ["Filiale", 69], ["Evidenze", 84], ["", 33]
  ];
  // The scroll of screens 1 and 2: the Stato and the Data Ass./Del. labels where the reference screenshots have them.
  const startingOffset = 181;
  const extendedOffset = 418;
  const menuItems = ["Avvia Lavorazione", "Visualizza Pratica", "Monitoraggio Pratica", "Sospendi", "Abbandona"];
  const opening = new Set(menuItems.slice(0, 2));
  // Hover boxes follow the pointer: reference 3 has the evidence box 11 px right of and 6 px below the
  // arrow tip (about 15 and 9 video px at 100% zoom).
  const pointerOffset = [11, 6];
  // Without a pointer (state 3) reference 3 has the box's left edge 10.8 px right of the B mark's centre (10.83 lands it on
  // the same layout unit as before).
  const restOffset = 10.83;
  let showCurrent = () => {};
  // The scroll bars of the panel shown now; a new panel stops watching the old ones.
  let resizing = [];

  // definitions: labels (content-sized columns) or [label, width] pairs (the empty table's measured widths).
  function header(table, definitions) {
    const group = document.createElement("colgroup");
    const row = table.createTHead().insertRow();
    definitions.forEach((definition) => {
      const [name, width] = Array.isArray(definition) ? definition : [definition];
      const col = document.createElement("col");
      if (width) col.style.width = width + "px";
      group.append(col);
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = name;
      if (name && name !== "Evidenze") th.append(icon("sort"));
      if (filters.has(name)) th.append(icon("filter"));
      row.append(th);
    });
    table.prepend(group);
    pin(row);
  }

  // ABI, NDG and Denom. follow the scroll part of the way; Evidenze and the actions stay at the right.
  function pin(row) {
    const count = row.cells.length;
    [...row.cells].forEach((cell, index) => {
      if (index < 4) cell.classList.add("bl-pin");
      else if (index >= count - 2) cell.classList.add("bl-pin-end");
    });
  }

  // The name's width in the list's font, measured as the truth measures it (list_font_metrics.json).
  let pen = null;
  function nameFits(name) {
    pen ??= document.createElement("canvas").getContext("2d");
    pen.font = nameFont;
    return pen.measureText(name).width <= nameLimit;
  }

  function icon(kind) {
    const span = document.createElement("span");
    span.className = "bl-icon-" + kind;
    span.setAttribute("aria-hidden", "true");
    return span;
  }

  function openableRow(row, open) {
    row.tabIndex = 0;
    row.addEventListener("click", event => {
      if (!event.target.closest("button")) open();
    });
    row.addEventListener("keydown", event => {
      if (event.target === row && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        open();
      }
    });
  }

  function searchText(value) {
    return String(value ?? "").normalize("NFD").replace(/\p{M}/gu, "")
      .toLocaleLowerCase("it").replace(/['’\s-]+/g, " ").trim();
  }

  function directory(root, practices, { openPractice }) {
    showCurrent = () => {};
    stopResizing();
    root.innerHTML = `
      <div class="bl-content bl-directory">
        <h2>Catalogo pratiche</h2>
        <div class="bl-directory-search" role="search">
          <label for="practice-query">Cerca per NDG, denominazione o numero pratica</label>
          <input id="practice-query" type="search" autocomplete="off">
          <button type="button" class="bl-clear" aria-label="Cancella ricerca">Cancella</button>
        </div>
        <p class="bl-matches" role="status"></p>
        <table aria-label="Catalogo pratiche">
          <thead><tr><th scope="col">NDG</th><th scope="col">Denominazione</th>
          <th scope="col">N° pratica</th><th scope="col">Tipo</th><th scope="col">Stato</th>
          <th scope="col">Fase</th><th scope="col">Creazione</th><th scope="col">Importo €</th>
          </tr></thead><tbody></tbody>
        </table>
        <nav class="bl-pagination" aria-label="Pagine dei risultati">
          <button type="button" aria-label="Pagina precedente">‹</button>
          <span class="bl-page-number"></span>
          <button type="button" aria-label="Pagina successiva">›</button>
        </nav>
      </div>`;
    const input = root.querySelector("input");
    const clear = root.querySelector(".bl-clear");
    const matches = root.querySelector(".bl-matches");
    const body = root.querySelector("tbody");
    const [previous, next] = root.querySelectorAll(".bl-pagination button");
    const pageNumber = root.querySelector(".bl-page-number");
    const pageSize = 8;
    let filtered = practices;
    let page = 0;

    function paint() {
      const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
      matches.textContent = filtered.length + (filtered.length === 1 ? " risultato" : " risultati");
      pageNumber.textContent = "Pagina " + (page + 1) + " di " + pages;
      previous.disabled = page === 0;
      next.disabled = page + 1 >= pages;
      clear.disabled = !input.value;
      body.replaceChildren();
      for (const p of filtered.slice(page * pageSize, (page + 1) * pageSize)) {
        const row = body.insertRow();
        for (const value of [p.ndg, p.name, p.number, p.type, p.state, p.phase, p.date, p.creditTotal]) {
          row.insertCell().textContent = value ?? "";
        }
        openableRow(row, () => openPractice(p));
      }
      if (!filtered.length) {
        const empty = body.insertRow().insertCell();
        empty.colSpan = 8;
        empty.textContent = "Nessun risultato";
      }
    }

    function filter() {
      const terms = searchText(input.value).split(" ").filter(Boolean);
      filtered = practices.filter(p => {
        const text = searchText([p.ndg, p.name, p.number].join(" "));
        return terms.every(term => text.includes(term));
      });
      page = 0;
      paint();
    }
    input.addEventListener("input", filter);
    clear.onclick = () => { input.value = ""; filter(); input.focus(); };
    previous.onclick = () => { page--; paint(); };
    next.onclick = () => { page++; paint(); };
    paint();
  }

  // A table in a native scroll container with the BStore bar drawn under it. The bar is dragged,
  // clicked or driven from the keyboard; the wheel scrolls too. The container follows the window
  // width and the table its content; while the panel is hidden both keep their last size, and a state
  // placed before the first measure is placed when the panel shows.
  // settle: how far each pinned column sticks left of where it starts (the identity columns of a table with rows).
  // onLayout runs after each measure, once the columns have their place.
  function scroller(scroll, bar, table, settle, onUser, onLayout = () => {}) {
    const thumb = bar.querySelector(".bl-thumb");
    let view = 791;
    let contentWidth = 0;
    let pinnedWidth = 0;
    let maximum = 0;
    let current = 0;
    let pending = null;
    let grab = null;
    bar.setAttribute("aria-valuemin", "0");

    function set(value) {
      if (!contentWidth) {
        pending = value;
        return;
      }
      current = Math.max(0, Math.min(Math.floor(maximum), Math.round(value)));
      scroll.scrollLeft = current;
      thumb.style.left = current * view / contentWidth + "px";
      bar.setAttribute("aria-valuenow", String(current));
      // The identity columns stick only while they fit in the container: past that they scroll out together
      // (reference 3 and MOL 01 01:30 at 1164 CSS px; at 1283 a long name never gets there, MOL 04 00:46).
      const stuck = Math.min(current, view - pinnedWidth - 1 + settle[3]);
      ["--bl-pin", "--bl-pin-ndg", "--bl-pin-name"].forEach((name, i) => {
        table.style.setProperty(name, screenPixels(Math.max(0, stuck - settle[i + 1])));
      });
      table.style.setProperty("--bl-last", screenPixels(current - maximum));
    }
    // A pinned cell ends up shifted by its translation minus the scroll offset; keep that in whole
    // screen pixels, or at a fractional zoom hairline seams open between neighbouring pinned cells.
    function screenPixels(value) {
      const zoom = scroll.currentCSSZoom || 1;
      const scrolled = scroll.scrollLeft;
      return Math.round((value - scrolled) * zoom) / zoom + scrolled + "px";
    }
    // Fractional widths: rounding them would move the right-pinned columns by up to a pixel. The first scrolling
    // column starts where the pinned ones end; its header is never moved.
    function measure() {
      const zoom = scroll.currentCSSZoom || 1;
      const box = table.getBoundingClientRect();
      if (!box.width) return;
      view = scroll.getBoundingClientRect().width / zoom || view;
      contentWidth = box.width / zoom;
      pinnedWidth = (table.tHead.rows[0].cells[4].getBoundingClientRect().left - box.left) / zoom;
      maximum = Math.max(0, contentWidth - view);
      // A table that fits has no bar, like a native one: the BStore table and narrow result rows in the calibration
      // screens at 90% (about 2120 CSS px wide).
      bar.hidden = maximum < 1;
      thumb.style.width = Math.min(view, view * view / contentWidth) + "px";
      bar.setAttribute("aria-valuemax", String(Math.floor(maximum)));
      set(pending ?? current);
      pending = null;
      onLayout();
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scroll);
    observer.observe(table);
    resizing.push(observer);
    function move(value) {
      const before = current;
      set(value);
      if (current !== before) onUser();
    }
    // Screen pixels, so a zoomed frame drags as fast as the pointer moves.
    const fromPointer = (event) => {
      const track = bar.getBoundingClientRect();
      return (event.clientX - track.left - grab) * contentWidth / track.width;
    };

    scroll.addEventListener("scroll", () => {
      if (scroll.scrollLeft !== current) move(scroll.scrollLeft);
    });
    scroll.addEventListener("wheel", (event) => {
      // A list taller than the window scrolls down with the wheel; only a sideways wheel moves its columns.
      if (!event.deltaX && scroll.closest(".bl-tall")) return;
      const delta = event.deltaX || event.deltaY;
      if (delta) {
        event.preventDefault();
        move(current + delta * (event.deltaMode === 1 ? 16 : 1));
      }
    }, { passive: false });
    bar.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      bar.focus();
      bar.setPointerCapture(event.pointerId);
      bar.classList.add("bl-dragging");
      const box = thumb.getBoundingClientRect();
      grab = event.target === thumb ? event.clientX - box.left : box.width / 2;
      if (event.target !== thumb) move(fromPointer(event));
    });
    bar.addEventListener("pointermove", (event) => {
      if (grab !== null) move(fromPointer(event));
    });
    const release = () => {
      grab = null;
      bar.classList.remove("bl-dragging");
    };
    bar.addEventListener("pointerup", release);
    bar.addEventListener("pointercancel", release);
    bar.addEventListener("keydown", (event) => {
      const steps = { ArrowLeft: -40, ArrowRight: 40, PageUp: -view, PageDown: view };
      const target = event.key === "Home" ? 0 : event.key === "End" ? maximum
        : event.key in steps ? current + steps[event.key] : null;
      if (target !== null) {
        event.preventDefault();
        move(target);
      }
    });
    return { set, offset: () => current };
  }

  function stopResizing() {
    resizing.forEach((observer) => observer.disconnect());
    resizing = [];
  }

  // One row per practice. Without results the list holds the practice of a direct link alone, as the
  // reference screenshots show it; with them it holds what Ricerca Pratica found, and filters are the
  // [label, value] criteria listed under "Filtri Attivi".
  function render(root, practice, { openPractice, onState, results: found = null, filters = [] }) {
    stopResizing();
    const listed = found ?? [practice];
    root.innerHTML = `
      <div class="bl-content">
        <details class="bl-filters">
          <summary>Filtri Attivi</summary>
          <div>NDG <span class="bl-filter-value" data-field="ndg"></span></div>
        </details>
        <div class="bl-result-count"></div>
        <details class="bl-legend"><summary>Legenda Icone</summary><div><b></b> <span></span></div></details>
        <div class="bl-scroll" id="bl-results-scroll"><table class="bl-results" aria-label="Elenco pratiche"></table></div>
        <div class="bl-bar bl-results-bar" role="scrollbar" tabindex="0" aria-orientation="horizontal"
          aria-controls="bl-results-scroll" aria-label="Scorri le colonne dell’elenco pratiche"><div class="bl-thumb"></div></div>
        <div id="bper-evidence-tooltip" class="bl-tooltip" role="tooltip" data-field="tooltip_evidenze_b" hidden></div>
        <div class="bl-tooltip bl-hint" role="tooltip" hidden></div>
        <div class="bl-menu" role="menu" aria-label="Azioni pratica" hidden>${menuItems
          .map((item) => `<button type="button" role="menuitem" tabindex="-1">${item}</button>`).join("")}</div>
        <div class="bl-actions"><span class="bl-page" aria-current="page">1</span>
          <span class="bl-export">ESPORTA IN EXCEL <span aria-hidden="true">⤓</span></span>
          <span class="bl-prints">RICHIEDI STAMPE</span>
        </div>
        <div class="bl-queue-title">Pratiche in attesa lavorazione in BStore</div>
        <div class="bl-empty-count">0 risultati</div>
        <div class="bl-empty-wrap" id="bl-queue-scroll"><table class="bl-empty" aria-label="Pratiche in attesa lavorazione in BStore"></table></div>
        <div class="bl-bar bl-empty-bar" role="scrollbar" tabindex="0" aria-orientation="horizontal"
          aria-controls="bl-queue-scroll" aria-label="Scorri le pratiche in attesa lavorazione in BStore"><div class="bl-thumb"></div></div>
      </div>`;

    const get = (selector) => root.querySelector(selector);
    if (found) {
      get(".bl-filters > div").replaceChildren(...filters.map(([label, value]) => {
        const line = document.createElement("div");
        const shown = document.createElement("span");
        shown.className = "bl-filter-value";
        shown.textContent = value;
        line.append(label + " ", shown);
        return line;
      }));
    } else {
      get(".bl-filter-value").textContent = practice.ndg;
    }
    get(".bl-result-count").textContent = listed.length + " risultati";
    const content = get(".bl-content");
    const tooltip = get("#bper-evidence-tooltip");
    const hint = get(".bl-hint");
    const menu = get(".bl-menu");
    const items = [...menu.querySelectorAll("button")];
    const table = get(".bl-results");
    // Like the empty BStore table, an empty result has no "N°" column (video 01:44).
    const definitions = listed.length ? columns : lowerColumns;
    header(table, definitions);
    const body = table.createTBody();
    if (!listed.length) {
      table.className = "bl-empty";
      const none = body.insertRow().insertCell();
      none.colSpan = definitions.length;
      none.textContent = "Nessun risultato";
    }
    table.classList.toggle("bl-selectable", listed.some((p) => selectable.has(p.state)));
    let menuFor = null;
    const rows = listed.map(addRow);
    const legend = rows.find((row) => row.hasTooltip);
    // Every calibration screen with a row shows the link, with or without an evidence code.
    get(".bl-legend").hidden = !rows.length;
    get(".bl-legend b").textContent = legend?.code ?? "";
    get(".bl-legend span").textContent = legend?.description ?? "";
    tooltip.textContent = legend?.description ?? "";
    // Each further row moves what follows the table 36 px down, and the page scrolls (spec section 5).
    const extra = Math.max(listed.length - 1, 0) * 36;
    root.classList.toggle("bl-tall", extra > 0);
    if (extra) content.style.setProperty("--bl-extra", extra + "px");

    function addRow(p) {
      const row = body.insertRow();
      const synthetic = Boolean(p.key && p.key !== "reference");
      const date = p.date;
      const code = p.evidence ?? "";
      const description = p.evidenceTooltip ?? "";
      const hasTooltip = Boolean(code && description);
      const values = [
        "", p.abi, p.ndg, p.name, p.number, p.typeCode ?? p.type,
        synthetic ? p.creditTotal : "", p.state, p.phase, date, p.assigned ?? date,
        p.assignee, "", "", p.region ?? (synthetic ? "" : "LI-DREG"),
        p.area ?? (synthetic ? "" : "SZ-AREA"), p.branch, "", ""
      ];
      const cells = values.map((value) => {
        const cell = row.insertCell();
        cell.textContent = value ?? "";
        return cell;
      });
      pin(row);
      // Where each extracted field shows, for the truth audit (bper-emulator/audit_truth.cjs).
      for (const [index, name] of [[2, "ndg"], [3, "denominazione"], [5, "tipo"], [7, "stato"], [8, "fase"], [9, "creazione"]]) {
        cells[index].dataset.field = name;
      }
      if (p.name && !nameFits(p.name)) {
        const cut = document.createElement("span");
        cut.className = "bl-cut";
        cut.textContent = p.name;
        cut.dataset.field = "denominazione";
        delete cells[3].dataset.field;
        cells[3].replaceChildren(cut);
      }
      if (selectable.has(p.state)) {
        const box = document.createElement("input");
        box.type = "checkbox";
        box.className = "bl-select";
        box.setAttribute("aria-label", "Seleziona pratica " + p.number);
        cells[0].append(box);
      }
      // Each code is a mark of its own in the cell's row of marks (B, BC, BM and V in the calibration screens), among
      // the other marks of an invented practice; the text reads as the truth writes it ("B V"). B's description belongs
      // to the B mark.
      const evidence = document.createElement(hasTooltip ? "button" : "span");
      evidence.className = "bl-codes";
      evidence.dataset.field = "evidenze";
      const codes = code.split(/\s+/).filter(Boolean);
      const others = otherMarks(p, codes.length);
      const marks = [];
      const place = (kind, text = "") => {
        const mark = document.createElement("span");
        mark.className = "bl-mark";
        mark.dataset.mark = kind;
        if (text) {
          if (marks.some((m) => m.textContent)) evidence.append(" ");
          mark.textContent = text;
        } else {
          mark.setAttribute("aria-hidden", "true");
        }
        evidence.append(mark);
        marks.push(mark);
      };
      for (const kind of ["clip", "note"]) if (others.has(kind)) place(kind);
      for (const part of codes) if (part !== "V") place(part, part);
      if (others.has("diamond")) place("diamond");
      for (const part of codes) if (part === "V") place(part, part);
      for (const kind of ["loop", "p"]) if (others.has(kind)) place(kind);
      const anchor = marks.find((mark) => mark.textContent === "B") ?? marks.find((mark) => mark.textContent);
      const badge = document.createElement("span");
      badge.className = "bl-version";
      badge.textContent = "2.0";
      cells[17].append(evidence, badge);
      const kebab = document.createElement("button");
      kebab.type = "button";
      kebab.className = "bl-kebab";
      kebab.textContent = "⋮";
      kebab.setAttribute("aria-label", "Azioni pratica " + p.number);
      kebab.setAttribute("aria-haspopup", "menu");
      kebab.setAttribute("aria-expanded", "false");
      cells[18].append(kebab);
      kebab.addEventListener("click", () => (menu.hidden || menuFor?.kebab !== kebab ? openMenu(kebab, p) : closeMenu(true)));
      if (hasTooltip) {
        const show = () => {
          tooltip.textContent = description;
          displayTooltip(true);
        };
        evidence.type = "button";
        evidence.classList.add("bl-evidence");
        evidence.setAttribute("aria-label", "Evidenze " + code);
        evidence.setAttribute("aria-describedby", "bper-evidence-tooltip");
        evidence.addEventListener("pointerenter", (event) => {
          follow(tooltip, event);
          show();
        });
        evidence.addEventListener("pointermove", (event) => follow(tooltip, event));
        evidence.addEventListener("pointerleave", () => displayTooltip(false));
        // Without a pointer the box takes the place reference 3 shows beside the B mark.
        evidence.addEventListener("focus", () => {
          if (!evidence.matches(":hover")) rest(anchor);
          show();
        });
        evidence.addEventListener("blur", () => displayTooltip(false));
        evidence.addEventListener("click", show);
        evidence.addEventListener("keydown", (event) => {
          if (event.key === "Escape") displayTooltip(false);
        });
      }
      // Denom., Tipo and Assegnata show their full value beside the pointer, at once.
      const hints = [[cells[3], p.name], [cells[5], p.typeName ?? p.type], [cells[11], p.assigneeName]];
      for (const [cell, text] of hints) {
        if (!text) continue;
        cell.classList.add("bl-has-hint");
        cell.addEventListener("pointermove", (event) => {
          hint.textContent = text;
          follow(hint, event);
          hint.hidden = false;
        });
        cell.addEventListener("pointerleave", () => { hint.hidden = true; });
      }
      return { code, description, hasTooltip, anchor };
    }

    const empty = get(".bl-empty-wrap .bl-empty");
    header(empty, lowerColumns);
    const emptyCell = empty.createTBody().insertRow().insertCell();
    emptyCell.colSpan = lowerColumns.length;
    emptyCell.textContent = "Nessun risultato";

    const resultsBar = get(".bl-results-bar");
    // The capture window shows reference screen 1, scrolled while the bar was held; elsewhere the list opens at its first
    // column with the bar idle, as the calibration elenco-01 screens and video 18:10 show it.
    // At 1164-1283 CSS px a whole name pushes Creazione (and Fase at 1164) under the pinned Evidenze there: those fields
    // come from other states, and the per-practice truth is the reference.
    // shortcut: the per-screen truth of screen 1 holds at capture scale only, replace if a screen-scale truth per state is needed
    const capture = Boolean(root.closest('[data-scale="capture"]'));
    const start = capture ? startingOffset : 0;
    let offset = start;
    let currentState = 1;
    // The mark the evidence tooltip rests beside when no pointer places it (state 3, keyboard focus).
    let resting = null;
    // No frame shows a table without rows scrolled: its columns stick where they start.
    const still = [0, 0, 0, 0];
    const upper = scroller(get(".bl-scroll"), resultsBar, table, listed.length ? settled : still, () => {
      offset = upper.offset();
      tooltip.hidden = true;
      closeMenu();
      publish();
    }, () => { if (resting && !tooltip.hidden) rest(resting); });
    const queue = scroller(get(".bl-empty-wrap"), get(".bl-empty-bar"), empty, still, () => {});

    function publish() {
      const next = !tooltip.hidden ? 3 : offset >= (start + extendedOffset) / 2 ? 2 : 1;
      if (next !== currentState) {
        currentState = next;
        onState(next);
      }
    }

    function displayTooltip(visible) {
      tooltip.hidden = !visible;
      publish();
    }
    // A viewport point in the coordinates of the list, which the simulator may show zoomed.
    function local(clientX, clientY) {
      const box = content.getBoundingClientRect();
      const zoom = content.currentCSSZoom || box.width / content.offsetWidth;
      return [(clientX - box.left) / zoom, (clientY - box.top) / zoom];
    }
    function follow(box, event) {
      const [x, y] = local(event.clientX, event.clientY);
      if (box === tooltip) resting = null;
      box.style.left = x + pointerOffset[0] + "px";
      box.style.top = y + pointerOffset[1] + "px";
    }
    // Reference 3, without a pointer: the box 10.8 px right of the B mark's centre, at the height list.css gives it. A panel
    // not shown yet has no boxes: the next measure places it.
    function rest(mark) {
      resting = mark;
      tooltip.style.top = "";
      const box = mark.getBoundingClientRect();
      tooltip.style.left = box.width ? local(box.left + box.width / 2, 0)[0] + restOffset + "px" : "";
    }
    content.addEventListener("pointermove", (event) => {
      delete resultsBar.dataset.held;
      if (!tooltip.hidden && !event.target.closest(".bl-evidence") &&
          !document.activeElement?.classList.contains("bl-evidence")) {
        displayTooltip(false);
      }
    });

    // The practice opens from the row's actions menu, never from a click on the row.
    function closeMenu(refocus = false) {
      if (menu.hidden) return;
      menu.hidden = true;
      menuFor.kebab.setAttribute("aria-expanded", "false");
      if (refocus) menuFor.kebab.focus();
    }
    // Before its menu the row waits (18:10.6-18:11.1): the table fades and the shell's ring turns over the row, in
    // the middle of the table's width. Clicks meanwhile change nothing.
    let busy = null;
    function openMenu(kebab, p) {
      closeMenu();
      const loading = window.BperLoading;
      if (!loading?.enabled) return showMenu(kebab, p);
      if (busy) return;
      const scroll = get(".bl-scroll").getBoundingClientRect();
      const row = kebab.closest("tr").getBoundingClientRect();
      const [x, y] = local(scroll.left + scroll.width / 2, row.top + row.height / 2);
      table.setAttribute("aria-busy", "true");
      content.insertAdjacentHTML("beforeend", '<i class="ld-ring" role="progressbar" aria-label="Caricamento in corso"></i>');
      const ring = content.lastElementChild;
      ring.style.left = x + "px";
      ring.style.top = y + "px";
      busy = loading.sequence([[loading.TIMES.rowBusy, () => {
        busy = null;
        ring.remove();
        table.removeAttribute("aria-busy");
        showMenu(kebab, p);
      }]]);
    }
    // Once closed the menu stays a moment at the window's top left, over the header (01:55.4, MOL 01 01:51.0).
    function ghost() {
      const loading = window.BperLoading;
      const host = root.closest("#application");
      if (!loading?.enabled || !host) return;
      const copy = menu.cloneNode(true);
      copy.classList.add("bl-ghost");
      copy.removeAttribute("role");
      copy.setAttribute("aria-hidden", "true");
      copy.style.left = copy.style.top = "0";
      copy.querySelectorAll("button").forEach(button => { button.disabled = true; });
      host.append(copy);
      loading.sequence([[loading.TIMES.ghost, () => copy.remove()]]);
    }
    function showMenu(kebab, p) {
      menuFor = { kebab, practice: p };
      const dots = kebab.getBoundingClientRect();
      const [x, y] = local(dots.left + dots.width / 2, dots.top + dots.height / 2);
      menu.style.left = x - 117 + "px";
      menu.style.top = y + 9 + "px";
      menu.hidden = false;
      kebab.setAttribute("aria-expanded", "true");
      items[0].focus();
    }
    menu.addEventListener("click", (event) => {
      const item = event.target.closest("button");
      if (!item) return;
      const opens = opening.has(item.textContent);
      if (opens) ghost();
      closeMenu();
      if (opens) openPractice(menuFor.practice);
    });
    menu.addEventListener("keydown", (event) => {
      const index = items.indexOf(document.activeElement);
      if (event.key === "Escape" || event.key === "Tab") {
        if (event.key === "Escape") event.preventDefault();
        closeMenu(event.key === "Escape");
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        items[(index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
      }
    });
    root.addEventListener("pointerdown", (event) => {
      if (!menu.contains(event.target) && !event.target.closest(".bl-kebab")) closeMenu();
    });

    // Placing a state never publishes one back: the caller already knows which state it shows.
    showCurrent = (step) => {
      currentState = step;
      // The end of the scroll is known once the table is measured (a panel rendered hidden waits for it).
      offset = step === 3 ? Infinity : step === 2 ? extendedOffset : start;
      upper.set(offset);
      queue.set(0);
      tooltip.hidden = step !== 3 || !rows[0]?.hasTooltip;
      resting = null;
      tooltip.style.left = tooltip.style.top = "";
      if (!tooltip.hidden) rest(rows[0].anchor);
      hint.hidden = true;
      closeMenu();
      // Reference states 1 and 2 were captured while the bar was being dragged, so there it shows its held look.
      if (step === 3 || !capture) delete resultsBar.dataset.held;
      else resultsBar.dataset.held = "";
    };
    showCurrent(1);
    // A fresh search shows its columns from the start, the bar idle (video 01:44).
    if (found) {
      offset = 0;
      upper.set(0);
      delete resultsBar.dataset.held;
    }
  }

  // nameLimit, settled, selectable, markShare, maxMarks and startingOffset are read by measure_list_font.cjs for the truth
  // (bper_simulator_truth.py).
  window.BperList = { render, directory, show: (step) => showCurrent(step), nameLimit, settled,
    selectable: [...selectable], markShare, maxMarks, startingOffset };
})();
