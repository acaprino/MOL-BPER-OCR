/* The BStore result list keeps the identification columns pinned for part of its travel. */
(() => {
  "use strict";

  const columns = [
    ["", 16], ["ABI", 84], ["NDG", 85], ["Denom.", 139], ["Numero", 80],
    ["Tipo", 76], ["Importo €", 88], ["Stato", 81], ["Fase", 76], ["Creazione", 88],
    ["Data Ass./Del.", 111], ["Assegnata", 91], ["Dest.", 61], ["Delib.", 65],
    ["D.R.", 74], ["Area", 78], ["Filiale", 80], ["Evidenze", 89], ["", 27]
  ];
  const filters = new Set(["ABI", "Tipo", "Stato", "Fase", "D.R.", "Area", "Filiale", "Evidenze"]);
  const lowerColumns = [
    ["", 36], ["ABI", 65], ["NDG", 83], ["Denom.", 83], ["Tipo", 75],
    ["Importo €", 88], ["Stato", 80], ["Fase", 76], ["Creazione", 88], ["Evidenze", 76], ["L.", 41]
  ];
  const startingOffset = 179;
  const extendedOffset = 418;
  let showCurrent = () => {};

  function header(table, definitions) {
    const group = document.createElement("colgroup");
    const row = table.createTHead().insertRow();
    definitions.forEach(([name, width]) => {
      const col = document.createElement("col");
      col.style.width = width + "px";
      group.append(col);
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = name;
      if (name && name !== "Evidenze") th.append(icon("sort"));
      if (filters.has(name)) th.append(icon("filter"));
      row.append(th);
    });
    table.prepend(group);
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
    root.innerHTML = `
      <div class="bl-content bl-directory">
        <h2>Ricerca pratica</h2>
        <div class="bl-directory-search" role="search">
          <label for="practice-query">Cerca per NDG, denominazione o numero pratica</label>
          <input id="practice-query" type="search" autocomplete="off">
          <button type="button" class="bl-clear" aria-label="Cancella ricerca">Cancella</button>
        </div>
        <p class="bl-matches" role="status"></p>
        <table aria-label="Elenco pratiche">
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

  function render(root, practice, { openPractice, onState }) {
    root.innerHTML = `
      <div class="bl-content">
        <details class="bl-filters">
          <summary>Filtri Attivi</summary>
          <div>NDG <span class="bl-filter-value"></span></div>
        </details>
        <div class="bl-result-count">1 risultati</div>
        <details class="bl-legend"><summary>Legenda Icone</summary><div><b></b> <span></span></div></details>
        <div class="bl-scroll"><table class="bl-results" aria-label="Elenco pratiche"></table></div>
        <input class="bl-slider" type="range" min="0" step="1" aria-label="Scorri le colonne dell’elenco pratiche">
        <div id="bper-evidence-tooltip" class="bl-tooltip" role="tooltip" hidden></div>
        <div class="bl-actions"><span class="bl-page" aria-current="page">1</span>
          <span class="bl-export">ESPORTA IN EXCEL <span aria-hidden="true">⤓</span></span>
          <span class="bl-prints">RICHIEDI STAMPE</span>
        </div>
        <div class="bl-queue-title">Pratiche in attesa lavorazione in BStore</div>
        <div class="bl-empty-count">0 risultati</div>
        <div class="bl-empty-wrap"><table class="bl-empty" aria-label="Pratiche in attesa lavorazione in BStore"></table></div>
        <div class="bl-empty-bar"></div>
      </div>`;

    const get = (selector) => root.querySelector(selector);
    get(".bl-filter-value").textContent = practice.ndg;
    const table = get(".bl-results");
    header(table, columns);
    const row = table.createTBody().insertRow();
    openableRow(row, openPractice);
    const synthetic = Boolean(practice.key && practice.key !== "reference");
    const date = practice.date;
    const evidenceCode = practice.evidence ?? "";
    const description = practice.evidenceTooltip ?? "";
    const hasTooltip = Boolean(evidenceCode && description);
    get(".bl-legend").hidden = !hasTooltip;
    get(".bl-legend b").textContent = evidenceCode;
    get(".bl-legend span").textContent = description;
    get(".bl-tooltip").textContent = description;
    const values = [
      "", practice.abi, practice.ndg, practice.name, practice.number, practice.type,
      synthetic ? practice.creditTotal : "", practice.state, practice.phase, date, practice.assigned ?? date,
      practice.assignee, "", "", practice.region ?? (synthetic ? "" : "LI-DREG"),
      practice.area ?? (synthetic ? "" : "SZ-AREA"), practice.branch, "", "⋮"
    ];
    const cells = values.map((value) => {
      const cell = row.insertCell();
      cell.textContent = value ?? "";
      return cell;
    });
    const evidence = document.createElement(hasTooltip ? "button" : "span");
    evidence.textContent = evidenceCode;
    const badge = document.createElement("span");
    badge.className = "bl-version";
    badge.textContent = "2.0";
    cells[17].append(evidence, badge);
    const empty = get(".bl-empty");
    header(empty, lowerColumns);
    const emptyCell = empty.createTBody().insertRow().insertCell();
    emptyCell.colSpan = lowerColumns.length;
    emptyCell.textContent = "Nessun risultato";

    const scroll = get(".bl-scroll");
    const slider = get(".bl-slider");
    const tooltip = get(".bl-tooltip");
    // Use design dimensions so a deep link also works while the parent panel is hidden.
    const maximum = columns.reduce((total, column) => total + column[1], 0) - 791;
    slider.max = String(maximum);
    let offset = startingOffset;
    let currentState = 1;

    function publish() {
      const next = !tooltip.hidden ? 3 : offset >= (startingOffset + extendedOffset) / 2 ? 2 : 1;
      if (next !== currentState) {
        currentState = next;
        onState(next);
      }
    }

    function position(value) {
      offset = Math.round(Math.max(0, Math.min(maximum, value)));
      slider.value = String(offset);
      scroll.scrollLeft = offset;
      table.style.setProperty("--bl-pin", Math.min(offset, 461) + "px");
      table.style.setProperty("--bl-last", offset - maximum + "px");
    }

    function scrollTo(value) {
      position(value);
      tooltip.hidden = true;
      publish();
    }

    function displayTooltip(visible) {
      tooltip.hidden = !visible;
      publish();
    }
    get(".bl-content").addEventListener("pointermove", (event) => {
      if (!tooltip.hidden && !evidence.contains(event.target) && document.activeElement !== evidence) {
        displayTooltip(false);
      }
    });
    if (hasTooltip) {
      evidence.type = "button";
      evidence.className = "bl-evidence";
      evidence.setAttribute("aria-label", "Evidenze " + evidenceCode);
      evidence.setAttribute("aria-describedby", "bper-evidence-tooltip");
      evidence.addEventListener("pointerenter", () => displayTooltip(true));
      evidence.addEventListener("pointerleave", () => displayTooltip(false));
      evidence.addEventListener("focus", () => displayTooltip(true));
      evidence.addEventListener("blur", () => displayTooltip(false));
      evidence.addEventListener("click", () => displayTooltip(true));
      evidence.addEventListener("keydown", (event) => {
        if (event.key === "Escape") displayTooltip(false);
      });
    }
    slider.addEventListener("input", () => scrollTo(slider.valueAsNumber));
    slider.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        scrollTo(offset + (event.key === "ArrowLeft" ? -40 : 40));
      }
    });
    scroll.addEventListener("scroll", () => {
      if (scroll.scrollLeft !== offset) scrollTo(scroll.scrollLeft);
    });
    scroll.addEventListener("wheel", (event) => {
      const horizontal = event.deltaX || event.deltaY;
      if (horizontal) {
        event.preventDefault();
        scrollTo(offset + horizontal * (event.deltaMode === 1 ? 16 : 1));
      }
    }, { passive: false });

    showCurrent = (step) => {
      currentState = step;
      position(step === 3 ? maximum : step === 2 ? extendedOffset : startingOffset);
      tooltip.hidden = step !== 3 || !hasTooltip;
    };
    showCurrent(1);
  }

  window.BperList = { render, directory, show: (step) => showCurrent(step) };
})();
