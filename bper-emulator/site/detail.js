/* Detail pages of the local practice viewer. Coordinates follow the reference window. */
(() => {
  "use strict";

  let root;
  let reportState;
  let activeStep;
  let activeDescription;

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function tab(label, step, className = "") {
    return `<button type="button" class="${className}" data-step="${step}">${label}</button>`;
  }

  function sidebar(subjects) {
    const groups = ["Verifica Preliminare", "Istruttoria", "Proposta", "Parere", "Delibera"];
    const expanded = subjects ? 0 : 1;
    const verification = [
      tab("Elenco Soggetti", 4, "pd-subitem pd-current"),
      '<span class="pd-subitem">Recupero Segnalazioni</span>'
    ];
    const investigation = [
      tab("Elenco Soggetti", 4, "pd-subitem pd-visited"),
      '<span class="pd-subitem pd-visited">Note Delibere Precedenti</span>',
      tab("Gestione Fidi e Garanzie", 5, "pd-subitem pd-current"),
      ...["Analisi Soggetti", "Situazione Banche", "Controlli di Fine Fase", "Iter e Chiusura"]
        .map(label => `<span class="pd-subitem">${label}</span>`)
    ];
    return `<aside class="pd-sidebar" data-sidebar="${subjects ? "subjects" : "credit"}">
      <div class="pd-navbox"><strong class="pd-navtitle">Navigatore</strong>
      ${groups.map((label, index) => {
        const className = "pd-group" + (expanded === index ? " pd-expanded" : index < expanded ? " pd-done" : "");
        const section = index < 2
          ? tab(label, index === 0 ? 4 : 5, className)
          : `<span class="${className}">${label}</span>`;
        return section + (expanded === index ? (subjects ? verification : investigation).join("") : "");
      }).join("")}
      <div class="pd-navtools" aria-hidden="true">${"<i></i>".repeat(5)}</div></div>
      <div class="pd-navbox"><strong class="pd-navtitle">Funzioni</strong>
      <div class="pd-quick"> &gt;&ensp;Gestione Documentale<br> + Stampe</div></div>
      <div class="pd-navbox"><strong class="pd-navtitle">Collegamenti Rapidi</strong>
      <div class="pd-quick">${["+ Schede WEB", "+ Bilanci", "+ Rating", "&gt; Gruppi Aziendali", "&gt; Acros WEB", "&gt; Web for Control Sistem", "&gt; Cerved New", "&gt; PRB - Pricing Risk Based", "&gt; CRM", "&gt; Titoli - PI.CO.", "&gt; CLM"].join("<br>")}</div></div>
    </aside>`;
  }

  function table(label, widths, headers, rows, className = "") {
    return `<table class="pd-table ${className}" aria-label="${label}"><colgroup>
      ${widths.map(w => `<col style="width:${w}px">`).join("")}</colgroup>
      <thead><tr>${headers.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(row => `<tr>${row.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  function subjectsPanel(p) {
    const dot = '<i class="pd-status" aria-label="Confermato"></i>';
    const rows = p.subjects.map((s, i) => [
      escapeText(s.ndg), escapeText(s.name), escapeText(s.role), "Verifica Preliminare",
      i === 0 ? dot : "", "", dot, ""
    ]);
    return `<section class="pd-subjects" data-panel="subjects">
      <div class="pd-date">Situazione al　 ${escapeText(p.created)}<span class="pd-bluebtn">Refresh</span></div>
      <h2 class="pd-bar">Elenco Soggetti</h2>
      ${table("Elenco Soggetti", [62,143,102,122,33,41,51,38],
        ["NDG", "Denominazione", "Ruolo", "Fase di recupero/inserimento", "Privacy", "Titolare effettivo", "Q.A.V.", "Azioni"], rows, "pd-subject-table")}
      <div class="pd-actions">${tab("Avvia Step Succ. &gt;", 5, "pd-bluebtn")}</div>
    </section>`;
  }

  function tipButton(row, step) {
    const label = escapeText(row.description);
    if (!row.tooltip) return label;
    return `<button type="button" class="pd-description" data-tooltip-step="${step}" data-tip="${escapeText(row.tooltip)}">${label}</button>`;
  }

  function totals(items) {
    return `<div class="pd-totals">${items.map(([label, value]) => `<span>${label}: <b>${value}</b></span>`).join("")}</div>`;
  }

  function financesPanel(p) {
    const creditHeads = ["N° Fido", "Rapporto", "Descrizione", "Scadenza", "Importo(€)", "Tipo Op."];
    const guaranteeHeads = ["N° Gar.", "Descrizione", "Fido", "NDG　Denominazione", "Imp. (€)/%", "Tipo Op."];
    const creditRows = p.fidi.map((row, i) => [
      escapeText(row.id), escapeText(row.account), tipButton(row, i === 0 ? 6 : 5),
      escapeText(row.due), escapeText(row.amount), escapeText(row.operation)
    ]);
    const guaranteeRows = p.guarantees.map((row, i) => [
      escapeText(row.id), tipButton(row, i < 2 ? 7 + i : 5),
      escapeText(row.creditId), escapeText(row.ndgName), escapeText(row.amount), escapeText(row.operation)
    ]);
    return `<section class="pd-credit" data-panel="credit">
      <div class="pd-finances">
      <div class="pd-fin-actions"><span class="pd-bluebtn">Refresh Rapporti</span> <span class="pd-bluebtn">Refresh Immobili</span></div>
      ${totals([["Totale accordato proposto", escapeText(p.creditTotal)], ["Totale accordato in essere", 0], ["Totale fidi sostituiti", 0], ["di cui di altri NDG", 0]])}
      <h2 class="pd-bar">FIDI</h2>
      <div class="pd-double">
      ${table("Fidi proposti", [42,68,59,39,52,48], creditHeads, creditRows, "pd-credit-table")}
      ${table("Fidi in essere", [39,36,48,50,49,48], ["N° Fido", "NDG", "Rapporto", "Descrizione", "Scadenza", "Importo(€)"], [])}
      </div>
      ${totals([["Totale garanzie proposte", escapeText(p.guaranteeTotal)], ["Totale garanzie in essere", 0], ["Totale garanzie estinte/liberate", 0]])}
      <h2 class="pd-bar">GARANZIE</h2>
      <div class="pd-double pd-guarantees">
      ${table("Garanzie proposte", [52,54,42,94,30,53], guaranteeHeads, guaranteeRows)}
      ${table("Garanzie in essere", [48,49,30,102,23], ["N° Gar.", "Descrizione", "Fido", "NDG　Denominazione", "Imp. (€)/%"], [])}
      </div></div>
      <div class="pd-strategy"><h2 class="pd-bar pd-fold">Strategie Politiche Creditizie</h2>
      <strong>SVILUPPO</strong><p>Perseguire un posizionamento competitivo e sostenibile nel tempo, attraverso la fidelizzazione del rapporto e lo sviluppo di nuovi impieghi</p></div>
    </section>`;
  }

  function notesPanel(p) {
    return `<section data-panel="notes" class="pd-notes">
      <div class="pd-note-card"><h2 class="pd-bar pd-fold">Nota della richiesta</h2>
      <div class="pd-byline">${escapeText(p.noteAuthor)}　del ${escapeText(p.created)}</div>
      <div class="pd-note-body">${escapeText(p.notes)}</div></div>
      <div class="pd-actions"><span class="pd-bluebtn">Procedi</span></div>
      <div class="pd-actions"><span class="pd-bluebtn">Avvia Step Succ. &gt;</span></div>
    </section>`;
  }

  function longDate(value) {
    const [day, month, year] = value.split("/").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    const part = options => date.toLocaleDateString("it-IT", {...options, timeZone: "UTC"});
    return part({weekday: "long"}) + ", " + part({day: "2-digit", month: "long", year: "numeric"});
  }

  function render(container, p, {onState}) {
    root = container;
    reportState = onState;
    activeDescription = null;
    const branch = escapeText([p.branch, p.branchName].filter(Boolean).join(" - "));
    root.innerHTML = `<div class="pd-window" tabindex="0" role="region" aria-label="Dettaglio della pratica">
      <div class="pd-page"><header class="pd-mast"><b aria-label="BPER" class="pd-brand">BPER</b>
      <span>${escapeText(longDate(p.created))} <time></time> - Benvenuto ${escapeText(p.operatorName)} (${escapeText(p.operatorId?.replace(/^U/, ""))}) | ${escapeText(p.officeCode || p.assignee)} | v1.0.1556 | <b class="pd-power">⏻</b></span></header>
      <nav class="pd-mainnav" aria-label="Sezioni PEF 2.0"><span>CRUSCOTTO PRATICHE</span><b aria-current="page">DETTAGLIO PRATICA</b><span>POLITICHE CREDITIZIE</span><span>ALTRE FUNZIONALITÀ</span></nav>
      <div class="pd-context"><span>Filiale: ${escapeText([p.branch, p.branchName].filter(Boolean).join("-"))}</span><span>Abi: ${escapeText(p.abi)} - Tipo Pratica: <b>${escapeText(p.type)}</b> - N° Pratica: ${escapeText(p.number)}</span></div>
      ${sidebar(true)}${sidebar(false)}
      <div class="pd-work"><h2 class="pd-bar pd-identity">NDG: ${escapeText(p.ndg)} - ${escapeText(p.name)}</h2>
      <div class="pd-identity-details"><div>Natura Giuridica: <b>PF PERSONA FISICA</b><br>Segmento Comportamentale:<br>Referente: <b> Non Disponibile</b><br>Cross Selling ABI: <b>5 su 16</b></div><div>Gruppo:<br><b>DE ST. NUOVA PRIVACY 02/2024</b></div><div>Classificazione: <b>VERDE - BONIS</b></div><div>Banca leader: <b>BPER</b><br>Filiale relazione: <b>${branch}</b></div></div>
      ${subjectsPanel(p)}
      <div class="pd-worktabs" data-panel="tabs">${tab("Gestione Fidi e Garanzie", 5)}<span>Note a Istruttoria</span>${tab("Note da Richiesta", 9)}<span>Dettaglio BPI</span></div>
      ${financesPanel(p)}${notesPanel(p)}</div>
      <div class="pd-tooltip" id="pd-tip" role="tooltip" hidden></div>
      </div></div>
      <label class="pd-scroll pd-vertical"><input type="range" min="0" max="100" value="0" aria-label="Scorrimento verticale del dettaglio"></label>
      <label class="pd-scroll pd-horizontal"><input type="range" min="0" max="100" value="0" aria-label="Scorrimento orizzontale del dettaglio"></label>`;
    const frame = root.querySelector(".pd-window");
    const vertical = root.querySelector(".pd-vertical input");
    const horizontal = root.querySelector(".pd-horizontal input");
    vertical.oninput = () => { frame.scrollTop = Number(vertical.value) * (frame.scrollHeight - frame.clientHeight) / 100; };
    horizontal.oninput = () => { frame.scrollLeft = Number(horizontal.value) * (frame.scrollWidth - frame.clientWidth) / 100; };
    frame.onscroll = () => {
      vertical.value = 100 * frame.scrollTop / Math.max(1, frame.scrollHeight - frame.clientHeight);
      horizontal.value = 100 * frame.scrollLeft / Math.max(1, frame.scrollWidth - frame.clientWidth);
    };
    root.onclick = event => {
      const target = event.target.closest("button");
      if (target?.dataset.step) navigate(Number(target.dataset.step));
      if (target?.dataset.tooltipStep) navigate(Number(target.dataset.tooltipStep), target);
    };
    function enterDescription(event) {
      const target = event.target.closest("[data-tooltip-step]");
      if (target && !target.contains(event.relatedTarget)) navigate(Number(target.dataset.tooltipStep), target);
    }
    function leaveDescription(event) {
      const target = event.target.closest("[data-tooltip-step]");
      if (target && target === activeDescription && !target.contains(event.relatedTarget)) navigate(5);
    }
    frame.addEventListener("mouseover", enterDescription);
    frame.addEventListener("focusin", enterDescription);
    frame.addEventListener("mouseout", leaveDescription);
    frame.addEventListener("focusout", leaveDescription);
    root.onkeydown = event => {
      if (event.key === "Escape" && activeDescription) {
        event.preventDefault();
        navigate(5);
      }
    };
    activeStep = null;
    show(4);
  }

  function navigate(step, description = null) {
    const changed = activeStep !== step;
    show(step, description);
    if (changed) reportState(step);
  }

  function show(step, description = null) {
    const page = step === 4 ? "subjects" : step === 9 ? "notes" : "credit";
    const frame = root.querySelector(".pd-window");
    if (frame.dataset.page !== page) frame.scrollTo(0, 0);
    activeStep = step;
    frame.dataset.page = page;
    root.querySelector("time").textContent = page === "subjects" ? "12:17" : page === "notes" ? "12:22" : "12:20";
    root.querySelectorAll("[data-sidebar]").forEach(node => {
      node.hidden = node.dataset.sidebar !== (page === "subjects" ? "subjects" : "credit");
    });
    root.querySelectorAll("[data-panel]").forEach(node => {
      node.hidden = node.dataset.panel === "tabs" ? page === "subjects" : node.dataset.panel !== page;
    });
    root.querySelectorAll(".pd-worktabs button").forEach(node => {
      node.classList.toggle("pd-selected-tab", node.dataset.step === (page === "notes" ? "9" : "5"));
    });
    const popup = root.querySelector(".pd-tooltip");
    activeDescription?.removeAttribute("aria-describedby");
    activeDescription = description || (step >= 6 && step <= 8
      ? root.querySelector(`[data-tooltip-step="${step}"]`) : null);
    popup.hidden = !activeDescription;
    popup.textContent = activeDescription?.dataset.tip || "";
    if (activeDescription) {
      activeDescription.after(popup);
      activeDescription.setAttribute("aria-describedby", popup.id);
    }
  }

  window.BperDetail = {render, show};
})();
