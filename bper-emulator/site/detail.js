/* Detail pages of the local practice viewer. Coordinates follow the reference window. The pages of the recordings
   beyond the reference screenshots (pef-extra.js) are hosted here when that script is loaded. */
(() => {
  "use strict";

  const query = new URLSearchParams(location.search);
  let root;
  let reportState;
  let activeStep;
  let activeDescription;
  let resizing;
  let practice;
  let viewOnly;
  let nav;
  let subjectIndex = 0;
  let drawn = "";
  let cancelRequest = () => {};
  const extra = () => window.BperPefExtra;

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function tab(label, step, className = "") {
    return `<button type="button" class="${className}" data-step="${step}">${label}</button>`;
  }

  // ---- the navigator (spec 9, 18.1-18.2 Layouts 1) ----
  // Groups by key: [label, items]; an item is [key, label, page], the page being one this emulator draws (subjects and
  // credit are the reference screens 4 and 5). Items no recording opened have none and do nothing.
  const GROUPS = {
    VEP: ["Verifica Preliminare", [["soggetti", "Elenco Soggetti", "subjects"], ["segnalazioni", "Recupero Segnalazioni", "segnalazioni"]]],
    RIC: ["Richiesta", [["soggetti", "Elenco Soggetti"], ["cliente", "Richiesta Cliente"], ["documenti", "Elenco Documenti"],
      ["stampe", "Stampe"], ["controlli", "Controlli di Fine Fase"]]],
    IST: ["Istruttoria", [["restituzione", "Note alla Restituzione"], ["soggetti", "Elenco Soggetti", "subjects"],
      ["delibere", "Note Delibere Precedenti", "delibere"], ["fidi", "Gestione Fidi e Garanzie", "credit"],
      ["analisi", "Analisi Soggetti"], ["banche", "Situazione Banche"], ["controlli", "Controlli di Fine Fase"],
      ["iter", "Iter e Chiusura"]]],
    PRO: ["Proposta", [["riepilogo", "Dati Riepilogo"], ["controlli", "Controlli di Fine Fase"], ["iter", "Iter e Proposta"]]],
    PAR: ["Parere", []],
    DEL: ["Delibera", [["controlli", "Controlli di Fine Fase"], ["delibera", "Delibera Pratica"]]],
  };
  // Drawn as <button> like in the markup the reference screens were matched with; the rest are spans with the button
  // role, so that the reference states keep their pixels.
  const BUTTONS = new Set(["VEP", "IST", "VEP.soggetti", "IST.soggetti", "IST.fidi"]);
  const PLAIN = { groups: ["VEP", "IST", "PRO", "PAR", "DEL"], phase: null, returned: false, body: "", request: false,
    done: false, until: null };
  // Accessible names of the toolbar's icons; the frames show no tooltip, only the exit's meaning is known (spec 18.5).
  const TOOLS = ["Step precedente", "Sospendi la pratica", "Elimina la pratica", "Aggiorna il navigatore", "Esci dalla pratica"];
  // Collegamenti Rapidi: the reference screenshots end at CLM, the full list goes on (spec 9; archive screenshots).
  const QUICK = ["+ Schede WEB", "+ Bilanci", "+ Rating", "&gt; Gruppi Aziendali", "&gt; Acros WEB", "&gt; Web for Control Sistem",
    "&gt; Cerved New", "&gt; PRB - Pricing Risk Based", "&gt; CRM", "&gt; Titoli - PI.CO.", "&gt; CLM", "&gt; RDB Reportistica",
    "+ Condizioni", "&gt; Adeguata verifica", "&gt; Visure ipocatastali", "&gt; Tool Allineamento Tassonomico"];

  // Istruttoria stops at nav.shape.until when set: the steps a practice still in it has reached.
  const itemsOf = group => {
    const items = GROUPS[group][1].filter(([key]) => key !== "restituzione" || nav.shape.returned);
    const end = group === "IST" && nav.shape.until ? items.findIndex(([key]) => key === nav.shape.until) + 1 : items.length;
    return items.slice(0, end);
  };
  // Past Istruttoria the inner tabs that are not open carry a tick (archive screenshots of approved practices).
  const tabsTicked = () => (nav.shape.done && !nav.shape.until) || ["PRO", "DEL"].includes(nav.shape.phase);
  const pageOf = id => itemsOf(id.split(".")[0]).find(([key]) => key === id.split(".")[1])?.[2];

  // The navigator a screen key or a direct link shows: the callout on the reference screen's page, the practice's
  // step on it too, or on its phase in visualizzazione; the groups of both open.
  function canonical(step) {
    const callout = step === 4 ? "VEP.soggetti" : "IST.fidi";
    const phase = nav.shape.phase;
    const progress = phase ? `${phase}.${phase === "IST" ? "fidi" : itemsOf(phase)[0][0]}` : callout;
    return { shape: nav.shape, progress, callout, expanded: new Set([callout, progress].map(id => id.split(".")[0])) };
  }

  // done, current or todo: groups and items before the practice's step are done (green check), its own is current
  // (orange badge), the later ones are to do (pencil).
  function statusOf(id) {
    if (nav.shape.done) return "done";
    const [group, item] = id.split(".");
    const [stepGroup, stepItem] = nav.progress.split(".");
    const order = nav.shape.groups;
    let distance = order.indexOf(group) - order.indexOf(stepGroup);
    if (!distance && item) {
      const keys = itemsOf(group).map(([key]) => key);
      distance = keys.indexOf(item) - keys.indexOf(stepItem);
    }
    return distance < 0 ? "done" : distance > 0 ? "todo" : "current";
  }

  function control(id, className, html, attributes) {
    const common = `class="${className}" data-status="${statusOf(id)}"${attributes}`;
    return BUTTONS.has(id) ? `<button type="button" ${common}>${html}</button>`
      : `<span role="button" tabindex="0" ${common}>${html}</span>`;
  }

  function groupHtml(group) {
    const status = statusOf(group);
    const open = nav.expanded.has(group);
    // Delibera carries the deliberating body on two more lines (MOL 05 20:59, 37:59).
    const body = group === "DEL" ? nav.shape.body : "";
    const className = "pd-group" + (status === "current" ? (open ? " pd-expanded" : " pd-expanded pd-closed")
      : status === "done" ? " pd-done" : "") + (open && status !== "current" ? " pd-open" : "") + (body ? " pd-body" : "");
    return control(group, className, body ? `${GROUPS[group][0]}<small>${body}</small>` : GROUPS[group][0],
      ` data-group="${group}" aria-expanded="${open}"`);
  }

  function itemHtml(group, [key, label]) {
    const id = `${group}.${key}`;
    const status = statusOf(id);
    const className = "pd-subitem" + (nav.callout === id ? " pd-current" : "") + ({ done: " pd-visited", current: " pd-now" }[status] || "");
    return control(id, className, label, ` data-nav="${id}"${nav.callout === id ? ' aria-current="page"' : ""}`);
  }

  // In visualizzazione the tools but the exit are greyed (MOL 05 06:53); otherwise only the back arrow, on the first step.
  function renderSidebar(keepFocus = false) {
    const sidebar = root.querySelector(".pd-sidebar");
    const focused = keepFocus && sidebar.contains(document.activeElement) ? document.activeElement.dataset : {};
    const tools = TOOLS.map((label, i) => {
      const disabled = viewOnly ? i < 4 : i === 0 && nav.progress === "VEP.soggetti";
      return `<i role="button" tabindex="0" aria-label="${label}" aria-disabled="${disabled}"${i === 4 ? ' data-action="exit"' : ""}></i>`;
    }).join("");
    const html = `<div class="pd-navbox"><strong class="pd-navtitle">Navigatore</strong>
      ${nav.shape.groups.map(group => groupHtml(group)
        + (nav.expanded.has(group) ? itemsOf(group).map(item => itemHtml(group, item)).join("") : "")).join("")}
      <div class="pd-navtools" role="toolbar" aria-label="Strumenti del navigatore">${tools}</div></div>
      <div class="pd-navbox"><strong class="pd-navtitle">Funzioni</strong>
      <div class="pd-quick"><a class="pd-doclink" href="#" data-docs-link> &gt;&ensp;Gestione Documentale</a><br> + Stampe${nav.shape.request
        ? '<br><a class="pd-doclink" href="#"> &gt;&ensp;Modulistica</a>' : ""}</div></div>
      <div class="pd-navbox"><strong class="pd-navtitle">Collegamenti Rapidi</strong>
      <div class="pd-quick">${QUICK.join("<br>")}</div></div>`;
    // Unchanged, the navigator is left alone: drawing it again shifts the antialiasing of a few pixels.
    if (html === drawn) return;
    sidebar.innerHTML = drawn = html;
    const again = focused.nav ? `[data-nav="${focused.nav}"]` : focused.group ? `[data-group="${focused.group}"]` : "";
    if (again) sidebar.querySelector(again)?.focus();
  }

  // A cell is its HTML, or [HTML, attributes] when it shows an extracted field (see field()).
  function table(label, widths, headers, rows, className = "") {
    return `<table class="pd-table ${className}" aria-label="${label}"><colgroup>
      ${widths.map(w => `<col style="width:${w}px">`).join("")}</colgroup>
      <thead><tr>${headers.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(row => `<tr>${row.map(c => Array.isArray(c) ? `<td${c[1]}>${c[0]}</td>` : `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  // Marks the cell of an extracted field for the truth audit (bper-emulator/audit_truth.cjs); row: its table row.
  function field(html, name, row = 0) {
    return [html, ` data-field="${name}"${row ? ` data-row="${row}"` : ""}`];
  }

  // In visualizzazione the buttons of this page and of Note da Richiesta are greyed too (calibration screenshots).
  // Opened from Istruttoria the list adds CR Obbligatoria (SI but for a cointestatario) and CR Presente after Titolare
  // effettivo (MOL video 02:04; training archive practice 52032077, whose columns give the widths); opened from Verifica
  // Preliminare it has the eight columns of reference screen 4 and of the other archive screenshots.
  function subjectsPanel(p, istruttoria = false) {
    const dot = '<i class="pd-status" aria-label="Confermato"></i>';
    const rows = p.subjects.map((s, i) => [
      ...(i < 4 ? [field(escapeText(s.ndg), `ndg_${i + 1}`), field(escapeText(s.name), `denominazione_${i + 1}`),
        field(escapeText(s.role), `ruolo_${i + 1}`)] : [escapeText(s.ndg), escapeText(s.name), escapeText(s.role)]),
      "Verifica Preliminare",
      i === 0 ? dot : "", "", ...(istruttoria ? [/^cointestat/i.test(s.role) ? "" : "SI", dot] : []), dot, ""
    ]);
    const headers = ["NDG", "Denominazione", "Ruolo", "Fase di recupero/inserimento", "Privacy", "Titolare effettivo",
      ...(istruttoria ? ["CR Obbligatoria", "CR Presente"] : []), "Q.A.V.", "Azioni"];
    return `<section class="pd-subjects" data-panel="subjects" data-under="${istruttoria ? "IST" : "VEP"}">
      <div class="pd-date">Situazione al　 ${escapeText(p.created)}<span class="pd-bluebtn" role="button" aria-disabled="${viewOnly}">Refresh</span></div>
      <h2 class="pd-bar">Elenco Soggetti</h2>
      ${table("Elenco Soggetti", istruttoria ? [54,116,91,109,33,36,62,36,28,27] : [62,143,102,122,33,41,51,38],
        headers, rows, "pd-subject-table")}
      <div class="pd-actions"><button type="button" class="pd-bluebtn" data-action="next" aria-disabled="${viewOnly}">Avvia Step Succ. &gt;</button></div>
    </section>`;
  }

  function tipButton(row, step) {
    const label = escapeText(row.description);
    if (!row.tooltip) return label;
    const filled = row.tooltipField ? ` data-tooltip-field="${row.tooltipField}"` : "";
    return `<button type="button" class="pd-description" data-tooltip-step="${step}" data-tip="${escapeText(row.tooltip)}"${filled}>${label}</button>`;
  }

  function totals(items) {
    return `<div class="pd-totals">${items.map(([label, value]) => `<span>${label}: <b>${value}</b></span>`).join("")}</div>`;
  }

  function financesPanel(p) {
    const creditHeads = ["N° Fido", "Rapporto", "Descrizione", "Scadenza", "Importo(€)", "Tipo Op."];
    const guaranteeHeads = ["N° Gar.", "Descrizione", "Fido", "NDG　Denominazione", "Imp. (€)/%", "Tipo Op."];
    const creditRows = p.fidi.map((row, i) => [
      field(escapeText(row.id), "n_fido", i + 1), field(escapeText(row.account), "rapporto", i + 1),
      field(tipButton(row, i === 0 ? 6 : 5), "descrizione", i + 1), field(escapeText(row.due), "scadenza", i + 1),
      field(escapeText(row.amount), "importo_euro", i + 1), field(escapeText(row.operation), "tipo_op", i + 1)
    ]);
    const guaranteeRows = p.guarantees.map((row, i) => [
      escapeText(row.id), tipButton(row, i < 2 ? 7 + i : 5),
      escapeText(row.creditId), escapeText(row.ndgName), escapeText(row.amount), escapeText(row.operation)
    ]);
    // In visualizzazione the Refresh buttons are drawn greyed (MOL 05 06:53). The lower blocks (pef-extra.js) start
    // under the capture view, so that the reference states keep their pixels (detail.css, .pd-credit-main).
    const refresh = label => `<span class="pd-bluebtn" role="button" aria-disabled="${viewOnly}">${label}</span>`;
    // A practice that passed through Richiesta can also restore its credit lines and add new ones (spec 10.2).
    const request = nav.shape.request;
    return `<section class="pd-credit" data-panel="credit"><div class="pd-credit-main">
      <div class="pd-finances">
      <div class="pd-fin-actions">${refresh("Refresh Rapporti")} ${refresh("Refresh Immobili")}${request ? ` ${refresh("Ripristina situazione in essere")}` : ""}</div>
      ${totals([["Totale accordato proposto", escapeText(p.creditTotal)], ["Totale accordato in essere", 0], ["Totale fidi sostituiti", 0], ["di cui di altri NDG", 0]])}
      <h2 class="pd-bar">FIDI</h2>
      <div class="pd-double">
      ${table("Fidi proposti", [42,68,59,39,52,48], creditHeads, creditRows, "pd-credit-table")}
      ${table("Fidi in essere", [39,36,48,50,49,48], ["N° Fido", "NDG", "Rapporto", "Descrizione", "Scadenza", "Importo(€)"], [])}
      </div>${request ? `<div class="pd-add">${refresh("Aggiungi Fido")}<label class="pd-revoke">Revisione dei Fidi a Revoca<input type="checkbox"${viewOnly ? " disabled" : ""}></label></div>` : ""}
      ${totals([["Totale garanzie proposte", escapeText(p.guaranteeTotal)], ["Totale garanzie in essere", 0], ["Totale garanzie estinte/liberate", 0]])}
      <h2 class="pd-bar">GARANZIE</h2>
      <div class="pd-double pd-guarantees">
      ${table("Garanzie proposte", [52,54,42,94,30,53], guaranteeHeads, guaranteeRows)}
      ${table("Garanzie in essere", [48,49,30,102,23], ["N° Gar.", "Descrizione", "Fido", "NDG　Denominazione", "Imp. (€)/%"], [])}
      </div>${request ? `<div class="pd-add">${refresh("Aggiungi Omnibus")}</div>` : ""}</div>
      <div class="pd-strategy"><h2 class="pd-bar pd-fold">Strategie Politiche Creditizie</h2>
      <strong>SVILUPPO</strong><p>Perseguire un posizionamento competitivo e sostenibile nel tempo, attraverso la fidelizzazione del rapporto e lo sviluppo di nuovi impieghi</p></div>
      </div>${extra()?.lowerBlocks(p, viewOnly) ?? ""}
    </section>`;
  }

  function notesPanel(p) {
    return `<section data-panel="notes" class="pd-notes">
      <div class="pd-note-card"><h2 class="pd-bar pd-fold">Nota della richiesta</h2>
      <div class="pd-byline">${escapeText(p.noteAuthor)}　del ${escapeText(p.created)}</div>
      <div class="pd-note-body" data-field="note_della_richiesta">${escapeText(p.notes)}</div></div>
      <div class="pd-actions"><span class="pd-bluebtn" role="button" aria-disabled="${viewOnly}">Procedi</span></div>
      <div class="pd-actions"><span class="pd-bluebtn" role="button" aria-disabled="${viewOnly}">Avvia Step Succ. &gt;</span></div>
    </section>`;
  }

  function longDate(value) {
    const [day, month, year] = value.split("/").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    const part = options => date.toLocaleDateString("it-IT", {...options, timeZone: "UTC"});
    return part({weekday: "long"}) + ", " + part({day: "2-digit", month: "long", year: "numeric"});
  }

  // options.visualizzazione: the practice opened in visualizzazione (spec 18.2 Layouts 1, 3). By default ?visualizzazione=1
  // or =0, else a real practice past Verifica Preliminare (pef-extra.js, viewOnlyOf).
  function render(container, p, {onState, visualizzazione = query.has("visualizzazione")
    ? query.get("visualizzazione") === "1" : extra()?.viewOnlyOf(p) ?? false}) {
    cancelRequest();
    root = container;
    reportState = onState;
    activeDescription = null;
    practice = p;
    viewOnly = visualizzazione;
    nav = { shape: extra()?.navigatorOf(p, viewOnly) ?? PLAIN };
    drawn = "";
    const branch = escapeText([p.branch, p.branchName].filter(Boolean).join(" - "));
    // In visualizzazione the header may name Istruttore and Proponente, each in a box that wraps on its own lines, and
    // state the legal form and the segment (pef-extra.js, headerOf).
    const head = extra()?.headerOf(p, viewOnly) ?? { instructor: "", proposer: "", legalForm: "", segment: "" };
    const person = name => `<b class="pd-person">${escapeText(name)}</b>`;
    const names = (head.instructor ? ` - Istruttore:${person(head.instructor)}` : "")
      + (head.proposer ? `</span><span class="pd-proposer">Proponente:${person(head.proposer)}` : "");
    root.innerHTML = `<div class="pd-window" tabindex="0" role="region" aria-label="Dettaglio della pratica">
      <div class="pd-page"><header class="pd-mast"><b aria-label="BPER" class="pd-brand">BPER</b>
      <span>${escapeText(longDate(p.created))} <time></time> - Benvenuto ${escapeText(p.operatorName)} (${escapeText(p.operatorId?.replace(/^U/, ""))}) | ${escapeText(p.officeCode || p.assignee)} | v1.0.1556 | <b class="pd-power">⏻</b></span></header>
      <nav class="pd-mainnav" aria-label="Sezioni PEF 2.0"><span>CRUSCOTTO PRATICHE</span><b aria-current="page">DETTAGLIO PRATICA</b><span>POLITICHE CREDITIZIE</span><span>ALTRE FUNZIONALITÀ</span></nav>
      <div class="pd-context${names ? " pd-named" : ""}"><span>Filiale: ${escapeText([p.branch, p.branchName].filter(Boolean).join("-"))}${names}</span><span>Abi: ${escapeText(p.abi)} - Tipo Pratica: <b data-field="tipo">${escapeText(p.type)}</b> - N° Pratica: ${escapeText(p.number)}</span></div>
      <aside class="pd-sidebar"></aside>
      <div class="pd-work"><h2 class="pd-bar pd-identity" data-field="ndg denominazione" data-template="NDG: {ndg} - {denominazione}">NDG: ${escapeText(p.ndg)} - ${escapeText(p.name)}</h2>
      <div class="pd-identity-details${head.legalForm || head.segment ? " pd-grown" : ""}"><div>Natura Giuridica: <b>${escapeText(head.legalForm || "PF PERSONA FISICA")}</b><br>Segmento Comportamentale:${head.segment ? ` <b>${escapeText(head.segment)}</b>` : ""}<br>Referente: <b> Non Disponibile</b><br>Cross Selling ABI: <b>5 su 16</b></div><div>Gruppo:<br><b>DE ST. NUOVA PRIVACY 02/2024</b></div><div>Classificazione: <b>VERDE - BONIS</b></div><div>Banca leader: <b>BPER</b><br>Filiale relazione: <b data-field="filiale_relazione">${branch}</b></div></div>
      ${subjectsPanel(p)}
      <div class="pd-worktabs" data-panel="tabs">${tab("Gestione Fidi e Garanzie", 5)}<span>Note a Istruttoria</span>${tab("Note da Richiesta", 9)}<span>Dettaglio BPI</span></div>
      ${financesPanel(p)}${notesPanel(p)}
      <section class="gd-page" data-panel="docs" aria-label="Gestione Documentale" hidden></section>
      <section class="rs-page" data-panel="segnalazioni" aria-label="Recupero Segnalazioni" hidden></section>
      <section class="nd-page" data-panel="delibere" aria-label="Note Delibere Precedenti" hidden></section></div>
      ${extra()?.LOGOUT ?? ""}
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
      // Links of the page lead nowhere here; "#" would change the screen of app.js.
      if (event.target.closest('a[href="#"]')) event.preventDefault();
      const target = event.target.closest('button, [role="button"]');
      if (target?.getAttribute("aria-disabled") === "true") return;
      const data = target?.dataset ?? {};
      // An inner tab is a PEF 2.0 request (loading.js); a description's tooltip opens at once.
      if (data.step) request(window.BperLoading?.TIMES.innerTab, () => navigate(Number(data.step)));
      if (data.tooltipStep) navigate(Number(data.tooltipStep), target, event.detail ? event : null);
      if (data.group) toggleGroup(data.group);
      if (data.nav) openItem(data.nav);
      if (data.action === "next") nextFromSubjects();
      if (data.action === "exit") openAlert();
      if (data.rs === "review") request(extra().TIMES.review, () => {
        subjectIndex = Math.min(subjectIndex + 1, extra().subjectsOf(practice).length - 1);
        showAlerts();
      });
      if (data.rs === "next") request(extra().TIMES.page, () => {
        nav = { shape: nav.shape, progress: "IST.soggetti", callout: "IST.soggetti", expanded: new Set(["IST"]) };
        renderSidebar();
        navigate(4);
      });
      if (data.nd === "next") request(extra().TIMES.credit, toCredit, true);
      if (data.alert === "cancel") closeAlert();
      if (data.alert === "confirm") request(extra().TIMES.exit, () => { closeAlert(); showExtra("logout"); });
      if (event.target.closest("[data-docs-link]")) {
        event.preventDefault();
        openDocuments();
      }
    };
    root.onchange = event => {
      if (event.target.id !== "rs-soggetto") return;
      subjectIndex = event.target.selectedIndex;
      request(extra().TIMES.review, showAlerts);
    };
    function enterDescription(event) {
      const target = event.target.closest("[data-tooltip-step]");
      if (target && !target.contains(event.relatedTarget)) {
        navigate(Number(target.dataset.tooltipStep), target, event.type === "mouseover" ? event : null);
      }
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
      const span = event.target.closest?.('[role="button"]:not(button)');
      if (span && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        span.click();
      } else if (event.key === "Escape" && root.querySelector(".pd-alert")) {
        event.preventDefault();
        closeAlert();
      } else if (event.key === "Escape" && activeDescription) {
        event.preventDefault();
        navigate(5);
      }
    };
    window.BperDocs?.render(root.querySelector('[data-panel="docs"]'), p, root);
    activeStep = null;
    show(4);
    // The panel and the page, not the frame: fitting the scrollbars resizes the frame itself. The page changes
    // height on Gestione Documentale, whose sections open and close.
    resizing?.disconnect();
    resizing = new ResizeObserver(fitScrollbars);
    resizing.observe(root);
    resizing.observe(root.querySelector(".pd-page"));
  }

  // A PEF 2.0 request (loading.js): the red wait and the ring for ms, then answer(); with notice, also "Recupero Fidi e
  // Garanzie in corso". At once without loading.js, in the capture window and with ?loading=off. A new request, a
  // screen key, the documents page or the exit drops the pending one.
  function request(ms, answer, notice = false) {
    cancelRequest();
    const loading = window.BperLoading;
    if (!loading?.enabled) {
      answer();
      return;
    }
    if (notice) showNotice(true);
    const stop = loading.run(root, ms, () => {
      showNotice(false);
      cancelRequest = () => {};
      answer();
    });
    cancelRequest = () => {
      stop();
      showNotice(false);
      cancelRequest = () => {};
    };
  }

  // Under the ring, which loading.js centres on the frame (main recording 02:52).
  function showNotice(on) {
    root.querySelector(".nd-notice")?.remove();
    if (!on) return;
    const frame = root.querySelector(".pd-window");
    root.insertAdjacentHTML("beforeend", extra().NOTICE);
    const notice = root.lastElementChild;
    notice.style.left = frame.offsetLeft + frame.clientWidth / 2 + "px";
    notice.style.top = frame.offsetTop + frame.clientHeight / 2 + "px";
  }

  // ---- in-page navigation: the URL keeps the reference screen, app.js hears only of screens 4 and 5 ----
  function toggleGroup(group) {
    nav.expanded[nav.expanded.has(group) ? "delete" : "add"](group);
    renderSidebar(true);
    fitPage();
    fitScrollbars();
  }

  // A navigator page opens under its callout once it answers (loading.js TIMES.navigator for the reference pages).
  function openItem(id) {
    const page = pageOf(id);
    if (page === "subjects" || page === "credit") {
      request(window.BperLoading?.TIMES.navigator, () => {
        nav.callout = id;
        renderSidebar(true);
        navigate(page === "subjects" ? 4 : 5);
      });
    } else if (page && extra()) {
      request(page === "segnalazioni" ? extra().TIMES.alerts : extra().TIMES.page, () => {
        nav.callout = id;
        renderSidebar(true);
        if (page === "segnalazioni") subjectIndex = 0;
        (page === "segnalazioni" ? showAlerts : showResolutions)();
      });
    }
  }

  // Elenco Soggetti, Avvia Step Succ. (main recording 02:44-02:53): Note Delibere Precedenti, then over it the notice
  // while Gestione Fidi e Garanzie loads, then that page. Without waits, Gestione Fidi e Garanzie at once.
  function nextFromSubjects() {
    if (!window.BperLoading?.enabled || !extra()) {
      toCredit();
      return;
    }
    request(extra().TIMES.page, () => {
      nav = { ...canonical(5), progress: "IST.delibere", callout: "IST.delibere" };
      renderSidebar();
      showResolutions();
      const stop = window.BperLoading.sequence([[extra().TIMES.notice, () => request(extra().TIMES.credit, toCredit, true)]]);
      cancelRequest = () => {
        stop();
        cancelRequest = () => {};
      };
    });
  }

  function toCredit() {
    nav = canonical(5);
    renderSidebar();
    navigate(5);
  }

  function showAlerts() {
    root.querySelector('[data-panel="segnalazioni"]').innerHTML = extra().alertsPage(practice, subjectIndex);
    showExtra("segnalazioni");
  }

  function showResolutions() {
    root.querySelector('[data-panel="delibere"]').innerHTML = extra().resolutionsPage(practice);
    showExtra("delibere");
  }

  // A page of pef-extra.js in the work area (or, for the logout, in place of the whole PEF 2.0 page).
  function showExtra(page) {
    setPage(page);
    clearDescription();
    fitPage();
    fitScrollbars();
  }

  function setPage(page) {
    const frame = root.querySelector(".pd-window");
    window.BperDocs?.close();
    if (frame.dataset.page !== page) frame.scrollTo(0, 0);
    frame.dataset.page = page;
    root.querySelector("time").textContent = page === "subjects" ? "12:17" : page === "notes" ? "12:22" : "12:20";
    root.querySelectorAll("[data-panel]").forEach(node => {
      node.hidden = node.dataset.panel === "tabs" ? !["credit", "notes"].includes(page) : node.dataset.panel !== page;
    });
  }

  function clearDescription() {
    activeDescription?.removeAttribute("aria-describedby");
    activeDescription = null;
    root.querySelector(".pd-tooltip").hidden = true;
  }

  // The pages of pef-extra.js are as long as what they show, like Gestione Documentale (docs.js); the reference pages
  // keep the lengths of the reference scrollbars (detail.css).
  function fitPage() {
    const frame = root.querySelector(".pd-window");
    const page = root.querySelector(".pd-page");
    if (frame.dataset.page === "docs") return;
    page.style.removeProperty("min-height");
    if (!["segnalazioni", "delibere", "logout"].includes(frame.dataset.page)) return;
    const bottom = [...root.querySelectorAll(".pd-work, .pd-sidebar")].filter(node => node.offsetParent)
      .reduce((most, node) => Math.max(most, node.offsetTop + node.offsetHeight), 0);
    if (bottom) page.style.minHeight = bottom + 14 + "px";
  }

  // ---- Avvertenza (MOL 06 08:22): over the navigator, its left edge 31.6 px into the page, centred on the frame's
  // height; nothing greyed behind it. It exists only while open, so it is the page's only alert dialog then. ----
  function openAlert() {
    if (!extra()) return;
    cancelRequest();
    closeAlert();
    root.insertAdjacentHTML("beforeend", extra().ALERT);
    placeAlert();
    root.querySelector('.pd-alert [data-alert="cancel"]').focus();
  }

  function placeAlert() {
    const dialog = root.querySelector(".pd-alert");
    const frame = root.querySelector(".pd-window");
    if (!dialog) return;
    dialog.style.left = frame.offsetLeft + 31.6 + "px";
    dialog.style.top = frame.offsetTop + (frame.offsetHeight - dialog.offsetHeight) / 2 + "px";
  }

  function closeAlert() {
    root.querySelector(".pd-alert")?.remove();
  }

  // Gestione Documentale (docs.js) replaces the work area under the identity box after its own wait. The URL and
  // the navigator keep the screen it was opened from, so the canonical states #1-#9 never show it.
  function openDocuments() {
    cancelRequest();
    closeAlert();
    window.BperDocs?.open(() => {
      const frame = root.querySelector(".pd-window");
      frame.dataset.page = "docs";
      root.querySelectorAll("[data-panel]").forEach(node => { node.hidden = node.dataset.panel !== "docs"; });
      fitScrollbars();
    });
  }

  // Each scrollbar shows only while the page overflows the frame that way (two passes: dropping
  // one gives the other direction more room), and its thumb is the visible share of its track.
  function fitScrollbars() {
    const frame = root.querySelector(".pd-window");
    const page = root.querySelector(".pd-page");
    if (!frame?.offsetWidth) return;
    frame.dataset.hbar = frame.dataset.vbar = "on";
    for (let pass = 0; pass < 2; pass++) {
      frame.dataset.hbar = page.offsetWidth > frame.clientWidth ? "on" : "off";
      frame.dataset.vbar = page.offsetHeight > frame.clientHeight ? "on" : "off";
    }
    const vertical = root.querySelector(".pd-vertical input");
    const horizontal = root.querySelector(".pd-horizontal input");
    vertical.style.setProperty("--pd-thumb-height", Math.round(vertical.clientHeight * frame.clientHeight / page.offsetHeight) + "px");
    horizontal.style.setProperty("--pd-thumb-width", Math.round(horizontal.clientWidth * frame.clientWidth / page.offsetWidth) + "px");
    placeAlert();
  }

  // pointer: the mouse event that opened a description's tooltip, if any.
  function navigate(step, description = null, pointer = null) {
    const changed = activeStep !== step;
    display(step, description, pointer);
    if (changed) reportState(step);
  }

  // A screen key, a direct link or the console: the reference screen, with the navigator it shows there.
  function show(step, description = null) {
    cancelRequest();
    closeAlert();
    nav = canonical(step);
    renderSidebar();
    display(step, description);
  }

  // Screen 4, 5-8 (a description's tooltip), or 9 in the work area; the navigator stays as it is.
  function display(step, description = null, pointer = null) {
    const page = step === 4 ? "subjects" : step === 9 ? "notes" : "credit";
    // Elenco Soggetti takes the columns of the group the navigator opened it from (subjectsPanel).
    const under = nav.callout === "IST.soggetti" ? "IST" : "VEP";
    const subjects = root.querySelector('[data-panel="subjects"]');
    if (step === 4 && subjects.dataset.under !== under) subjects.outerHTML = subjectsPanel(practice, under === "IST");
    setPage(page);
    activeStep = step;
    root.querySelectorAll(".pd-worktabs button").forEach(node => {
      node.classList.toggle("pd-selected-tab", node.dataset.step === (page === "notes" ? "9" : "5"));
    });
    root.querySelectorAll(".pd-worktabs > *").forEach(node => {
      if (tabsTicked() && !node.classList.contains("pd-selected-tab")) node.dataset.status = "done";
      else delete node.dataset.status;
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
    fitPage();
    fitScrollbars();
    placeTooltip(popup, pointer);
  }

  // At native scale a description's tooltip is the browser's own: the archive's 21 tooltip screenshots show Windows
  // tooltips, a 25 px box in Segoe UI 12 px at 90% and 100% alike, 20 device px under the pointer with its left edge at
  // it. Without a pointer (a screen key, the keyboard) the pointer is taken 80% across the description's cell and 20%
  // down it, where those tooltips put it on average. The capture window keeps the reference screenshots' box.
  function placeTooltip(popup, pointer) {
    const native = root.closest("#frame")?.dataset.scale === "native";
    popup.classList.toggle("pd-native-tip", native);
    popup.style.removeProperty("left");
    popup.style.removeProperty("top");
    if (!native || !activeDescription) return;
    const cell = activeDescription.closest("td");
    const box = cell.getBoundingClientRect();
    const scale = box.width / cell.offsetWidth;  // screen px per page px: the frame's zoom
    const device = 1 / devicePixelRatio;  // screen px per device px
    const x = pointer ? pointer.clientX : box.left + 0.8 * box.width;
    const y = pointer ? pointer.clientY : box.top + 0.2 * box.height;
    popup.style.setProperty("--pd-device", device / scale + "px");
    popup.style.left = (x - box.left) / scale - cell.clientLeft + "px";
    popup.style.top = (y + 20 * device - box.top) / scale - cell.clientTop + "px";
  }

  window.BperDetail = {render, show};
})();
