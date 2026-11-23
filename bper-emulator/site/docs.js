/* Gestione Documentale, the PEF 2.0 page listing every subject's documents, and the PDF viewer it embeds.
   detail.js hosts it in the work area, under the identity box. Only the recording shows this page (spec 10.4), so
   the documents and their PDF pages are invented, derived from the practice: the subjects and credits of its profile
   give the bars and sections, a hash of its key picks the documents and their acquisition. Lengths are reference
   px, like detail.css. */
(() => {
  "use strict";

  const query = new URLSearchParams(location.search);
  // Waits as the recording shows them (spec 9 and 10.4); none in the capture window and with ?loading=off.
  const DELAY = query.get("capture") === "1" || query.get("loading") === "off"
    ? null : { page: 1500, file: 1000, blank: 700, toast: 4200, tip: 500 };

  const ANAG = "Documenti anagrafici", INCOME = "Documenti reddituali e contabili",
    ASSETS = "Documenti patrimoniali", PRODUCT = "Documentazione specifica prodotto";
  const IDENTITY = "Carta d'identità, passaporto o patente di guida, fronte e retro";
  const LAND = "Si richiede la visura degli immobili di proprietà, se presenti";
  // [category, type, code (O, OA, E, EA), group of alternatives, info tooltip]. Invented, in the page's style.
  const PERSON = [
    [ANAG, "Documento di identità in corso di validità", "O", "", IDENTITY],
    [ANAG, "Tessera sanitaria con codice fiscale", "O", "", ""],
    [ANAG, "Mod. 07.31.0412 - Autocertificazione dello stato di famiglia", "OA", "14", "In alternativa al certificato rilasciato dal Comune"],
    [ANAG, "Certificato di stato di famiglia rilasciato dal Comune", "OA", "14", ""],
    [ANAG, "Mod. 07.31.0418 - Dichiarazione del regime patrimoniale", "OA", "15", "Richiesta ai richiedenti coniugati o uniti civilmente"],
    [ANAG, "Estratto dell'atto di matrimonio", "OA", "15", ""],
    [ANAG, "Certificato di residenza", "E", "", "Se la residenza è diversa da quella del documento di identità"],
    [ANAG, "Permesso di soggiorno per cittadini non comunitari", "E", "", "Obbligatorio per i cittadini di paesi esterni all'Unione Europea"],
    [INCOME, "Ultime due buste paga", "O", "", "Per i lavoratori dipendenti, le due mensilità più recenti"],
    [INCOME, "Certificazione Unica dell'ultimo anno", "O", "", "Si richiede la Certificazione Unica rilasciata dal datore di lavoro"],
    [INCOME, "Dichiarazione dei redditi con ricevuta di presentazione", "EA", "21", "Per i lavoratori autonomi, in alternativa alla Certificazione Unica"],
    [INCOME, "Estratti conto degli ultimi tre mesi", "E", "", ""],
    [INCOME, "Mod. 07.31.0436 - Prospetto dei finanziamenti in corso presso altri istituti", "O", "", "Indicare rata e debito residuo di ogni finanziamento"],
    [ASSETS, "Visura catastale degli immobili posseduti", "E", "", LAND],
    [ASSETS, "Rendiconto del deposito titoli", "E", "", ""],
  ];
  const GUARANTOR = [
    [ANAG, "Documento di identità in corso di validità", "O", "", IDENTITY],
    [ANAG, "Tessera sanitaria con codice fiscale", "O", "", ""],
    [ANAG, "Permesso di soggiorno per cittadini non comunitari", "E", "", "Obbligatorio per i cittadini di paesi esterni all'Unione Europea"],
    [ANAG, "Mod. 07.31.0418 - Dichiarazione del regime patrimoniale [richiesta al terzo datore di ipoteca]", "EA", "37", ""],
    [INCOME, "Certificazione Unica dell'ultimo anno", "O", "", "Si richiede la Certificazione Unica rilasciata dal datore di lavoro"],
    [INCOME, "Mod. 07.31.0441 - Dichiarazione di consenso del garante", "O", "", "Firmata dal garante in presenza dell'operatore"],
    [ASSETS, "Visura catastale degli immobili posseduti", "E", "", LAND],
  ];
  const MORTGAGE = [
    [PRODUCT, "Mod. 07.12.0207 - Richiesta di perizia sottoscritta", "O", "", ""],
    [PRODUCT, "Simulazione della rata e del rapporto rata/reddito", "O", "", "La simulazione stampata e consegnata al cliente"],
    [PRODUCT, "Visura catastale dell'immobile in garanzia", "O", "", ""],
    [PRODUCT, "Compromesso o proposta d'acquisto accettata", "O", "", "Con il prezzo pattuito e la data prevista per il rogito"],
    [PRODUCT, "Atto di provenienza dell'immobile", "E", "", "Si richiede l'ultimo atto di acquisto dell'immobile in garanzia"],
    [PRODUCT, "Attestato di prestazione energetica dell'immobile", "E", "", "Necessario per i mutui con finalità di efficienza energetica"],
    [PRODUCT, "Planimetria catastale aggiornata", "E", "", ""],
    [PRODUCT, "Preventivo dei lavori di ristrutturazione", "E", "", "Per i mutui con finalità di ristrutturazione"],
    [PRODUCT, "Polizza incendio e scoppio sull'immobile", "E", "", "Con vincolo a favore della banca"],
    [PRODUCT, "Mod. 07.12.0215 - Informativa sulla consulenza assicurativa", "E", "", ""],
  ];
  const LOAN = [
    [PRODUCT, "Mod. 07.14.0102 - Modulo di richiesta del prestito", "O", "", ""],
    [PRODUCT, "Simulazione della rata e del rapporto rata/reddito", "O", "", "La simulazione stampata e consegnata al cliente"],
    [PRODUCT, "Preventivo o fattura del bene finanziato", "O", "", "Intestato al richiedente, con l'importo dell'intervento"],
    [PRODUCT, "Documento di sintesi firmato per accettazione", "E", "", ""],
    [PRODUCT, "Mod. 07.14.0110 - Informativa sulla polizza a protezione del credito", "E", "", ""],
  ];
  const OTHER = [["Altro", "Altro", "E", "", ""]];
  const TOWNS = ["MODENA (MO)", "CARPI (MO)", "SASSUOLO (MO)", "REGGIO EMILIA (RE)", "PARMA (PR)", "FERRARA (FE)",
    "LUCCA (LU)", "BOLOGNA (BO)", "IMOLA (BO)", "CESENA (FC)"];
  const STREETS = ["VIA DEI MILLE", "VIA GIUSEPPE VERDI", "VIALE DELLA REPUBBLICA", "VIA ROMA", "VIA DANTE ALIGHIERI",
    "VIA DEL LAVORO", "VIA GARIBALDI", "VIA DELLE ROSE"];

  let ctx = null;
  let timers = [];

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  // FNV-1a of the seed, then mulberry32: the same practice always gets the same documents.
  function random(seed) {
    let state = 2166136261;
    for (const char of String(seed)) state = Math.imul(state ^ char.charCodeAt(0), 16777619);
    return () => {
      state = (state + 0x6d2b79f5) | 0;
      let t = Math.imul(state ^ (state >>> 15), 1 | state);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shiftDate(value, days) {
    const [day, month, year] = String(value).split("/").map(Number);
    if (!year) return value;
    const date = new Date(Date.UTC(year, month - 1, day - days));
    return date.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
  }

  // [{ndg, name, role, groups: [{title, rows: [{category, type, code, group, tip, note, acquired, date}]}]}]
  function documentsOf(practice) {
    const next = random(practice.key + "|" + practice.number);
    const lastDay = Math.floor(next() * 3) + 1;
    let first = true;
    function rows(catalog) {
      const chosen = catalog.filter(([, , code]) => code.startsWith("O") || next() < 0.75);
      // One document of a group of alternatives is enough: at most one of them is acquired.
      const alternatives = {};
      return chosen.map(([category, type, code, group, tip]) => {
        let acquired;
        if (code === "OA") {
          const pick = alternatives[group] ??= { at: next() < 0.9 ? Math.floor(next() * 2) : -1, seen: 0 };
          acquired = pick.seen++ === pick.at;
        } else {
          // The first mandatory document of the practice is always there, so every practice has one to open.
          acquired = code === "O" ? first || next() < 0.8 : next() < 0.3;
        }
        if (code === "O") first = false;
        const date = acquired ? shiftDate(practice.created, next() < 0.8 ? lastDay : lastDay + 1 + Math.floor(next() * 5)) : "";
        const note = acquired && category === "Altro" ? "Estratto conto contributivo" : "";
        return { category, type, code, group, tip, note, acquired, date };
      });
    }
    // A profile without its Elenco Soggetti (some archive practices) still has its holder.
    const subjects = practice.subjects.length ? practice.subjects
      : [{ ndg: practice.ndg, name: practice.name, role: "Richiedente" }];
    return subjects.map(subject => {
      const groups = [];
      if (/garant|pegno/i.test(subject.role)) groups.push({ title: "Documenti GARANTE", rows: rows(GUARANTOR) });
      else if (!/richiedente/i.test(subject.role) || !subject.name.includes(",")) {
        // A joint account (names joined by a comma) has no personal documents of its own.
        groups.push({ title: "Documenti CONTROPARTE", rows: rows(PERSON) });
      }
      if (/richiedente/i.test(subject.role)) {
        for (const credit of practice.fidi) {
          const product = String(credit.tooltip || credit.description).replace(/^\s*\d+\s*-\s*/, "");
          groups.push({ title: `Documenti relativi al Fido ${credit.id} ${product}`,
            rows: rows(/^M/i.test(credit.description) ? MORTGAGE : LOAN) });
        }
        groups.push({ title: "Documenti ALTRO", rows: rows(OTHER) });
      }
      return { ndg: subject.ndg, name: subject.name, role: subject.role, groups };
    });
  }

  // ---- loading: red line under the mast and a navy spinner over the frame, as on every PEF 2.0 request ----
  function later(ms, action) {
    if (!DELAY) return action();
    const id = setTimeout(() => { timers = timers.filter(t => t !== id); action(); }, ms);
    timers.push(id);
  }

  function loading(on) {
    const { root } = ctx;
    root.querySelector(".gd-wait")?.remove();
    root.querySelector(".gd-spinner")?.remove();
    if (!on) return;
    root.querySelector(".pd-page").insertAdjacentHTML("beforeend",
      '<span class="gd-wait" role="status">Attendere... caricamento in corso</span>');
    // Centred on what the frame shows, like the original's fixed spinner inside its iframe.
    const frame = root.querySelector(".pd-window");
    root.insertAdjacentHTML("beforeend", '<i class="gd-spinner" role="progressbar" aria-label="Caricamento in corso"></i>');
    const spinner = root.querySelector(".gd-spinner");
    spinner.style.left = frame.offsetLeft + frame.clientWidth / 2 + "px";
    spinner.style.top = frame.offsetTop + frame.clientHeight / 2 + "px";
  }

  // A PEF 2.0 request: the wait, then the new content at the top of the frame.
  function request(ms, action) {
    if (DELAY) loading(true);
    later(ms, () => {
      loading(false);
      ctx.root.querySelector(".pd-window").scrollTo(0, 0);
      action();
      fitPage();
    });
  }

  // The work area and the navigator are absolutely placed: the page grows to the longer of them, so the frame
  // scrolls to the end of the list (or of the navigator, beside the short viewer).
  function fitPage() {
    const page = ctx.root.querySelector(".pd-page");
    const bottom = [...ctx.root.querySelectorAll(".pd-work, .pd-sidebar:not([hidden])")]
      .reduce((most, node) => Math.max(most, node.offsetTop + node.offsetHeight), 0);
    page.style.minHeight = ctx.section.hidden ? "" : bottom + 14 + "px";
  }

  // ---- the list ----
  const CHECK = (label, attributes = "") => `<input type="checkbox" class="gd-check" aria-label="${label}"${attributes}>`;

  function documentRow(row, place) {
    const type = escapeText(row.type);
    const tip = row.tip ? `<button type="button" class="gd-info" aria-label="Informazioni" data-tip="${escapeText(row.tip)}"></button>` : "";
    const actions = row.acquired
      ? `<button type="button" class="gd-file" aria-label="Visualizza ${type}" data-doc="${place}"></button><i class="gd-unlink" aria-hidden="true"></i>`
      : '<i class="gd-clip" aria-hidden="true"></i><i class="gd-link" aria-hidden="true"></i>';
    const code = escapeText(row.code);
    return `<tr data-category="${escapeText(row.category)}" data-code="${code}" data-acquired="${row.acquired ? "si" : "no"}">
      <td>${escapeText(row.category)}</td><td>${type}</td><td${code.startsWith("O") ? ' class="gd-must"' : ""}>${code}</td>
      <td>${escapeText(row.group)}</td><td>${tip}</td><td>${escapeText(row.note)}</td>
      <td>${CHECK("Stampa", row.acquired ? " disabled" : "")}</td>
      <td>${CHECK("Acquisito", row.acquired ? " disabled checked" : " disabled")}</td><td>${escapeText(row.date)}</td><td>${actions}</td></tr>`;
  }

  // Column widths as the original's automatic layout made them (02m59s, 03m55s): the type column takes what is
  // left, and a table of product documents has a wider category and its codes a little further right.
  const COLUMNS = [61.1, 36.4, 35.7, 30.2, 58.4, 34.3, 37.1, 60.5, 58.8];
  const PRODUCT_COLUMNS = [70, 37.8, 35.7, 30.2, 58.4, 34.3, 37.1, 60.5, 56];

  // place: "<subject>.<group>" of the rows, so a file button finds its document.
  function table(rows, place, product) {
    const [category, ...rest] = product ? PRODUCT_COLUMNS : COLUMNS;
    return `<table class="gd-table"><colgroup><col style="width:${category}px"><col>${rest
      .map(w => `<col style="width:${w}px">`).join("")}</colgroup>
      <thead><tr><th scope="col">Categoria</th><th scope="col">Tipologia</th><th scope="col">Obbl.<br>doc.</th>
      <th scope="col">Grup.<br>Altern.</th><th scope="col"><span class="gd-hidden">Informazioni</span></th>
      <th scope="col">Descrizione</th><th scope="col">Stampa</th><th scope="col">Acquisito</th><th scope="col">Data Acq</th>
      <th scope="col"><span class="gd-hidden">Azioni</span></th></tr></thead>
      <tbody>${rows.map((row, i) => documentRow(row, place + "." + i)).join("")}</tbody></table>`;
  }

  function fold(tag, label, open, body, extra = "") {
    return `<${tag} class="gd-head"><button type="button" aria-expanded="${open}">${label}</button>${extra}</${tag}>
      <div class="gd-body"${open ? "" : " hidden"}>${body}</div>`;
  }

  function option(values) {
    return ["Seleziona...", ...values].map(v => `<option>${escapeText(v)}</option>`).join("");
  }

  function filter(categories) {
    const box = (label, code) => `<label class="gd-checklabel">${label}${CHECK(label, ` data-code="${code}"`)}</label>`;
    return `<div class="gd-filter">
      <label class="gd-category">Categoria <select>${option(categories)}</select></label>
      <label class="gd-print-filter">Stampa <select>${option(["Sì", "No"])}</select></label>
      <label class="gd-acquired">Acquisito <select>${option(["Sì", "No"])}</select></label>
      <span class="gd-mandatory">Obbligatorietà documenti</span>
      ${box("Obbligatori", "O")}${box("Obbligatori Alternativi", "OA")}${box("Eventuali Alternativi", "EA")}${box("Eventuali", "E")}
      <button type="button" class="gd-reset" disabled>Reset</button><button type="button" class="pd-bluebtn gd-apply">Applica</button>
    </div>`;
  }

  function showList() {
    const { section, practice, documents } = ctx;
    const categories = [...new Set(documents.flatMap(s => s.groups.flatMap(g => g.rows.map(r => r.category))))];
    const addList = '<i class="gd-addlist" aria-hidden="true"></i>';
    section.dataset.phase = "list";
    section.innerHTML = `<div class="gd-print">Data stampa:&ensp;${escapeText(practice.created)}
      <button type="button" class="pd-bluebtn">Stampa Lista per il Cliente</button><button type="button" class="pd-bluebtn">Salva Allegati</button></div>
      <div class="gd-box"><section class="gd-panel">${fold("h3", "Filtro Documenti", true, filter(categories))}</section>
      ${documents.map((subject, i) => `<section class="gd-panel gd-subject">${fold("h3",
        escapeText(`${subject.ndg} - ${subject.name} - ${subject.role}`), i === 0,
        subject.groups.map((group, g) => `<section class="gd-group">${fold("h4", escapeText(group.title), true,
          table(group.rows, i + "." + g, group.rows.every(row => row.category === PRODUCT)))}</section>`).join(""), addList)}</section>`).join("")}</div>`;
  }

  function applyFilter() {
    const { section } = ctx;
    const [category, printable, acquired] = [...section.querySelectorAll(".gd-filter select")].map(s => s.selectedIndex ? s.value : "");
    const codes = [...section.querySelectorAll(".gd-filter [data-code]:checked")].map(box => box.dataset.code);
    for (const row of section.querySelectorAll(".gd-table tbody tr")) {
      const done = row.dataset.acquired === "si";
      row.hidden = (category && row.dataset.category !== category) || (codes.length && !codes.includes(row.dataset.code)) ||
        (acquired && (acquired === "Sì") !== done) || (printable && (printable === "Sì") === done);
    }
    section.querySelector(".gd-reset").disabled = !(category || printable || acquired || codes.length);
  }

  function resetFilter() {
    ctx.section.querySelectorAll(".gd-filter select").forEach(select => { select.selectedIndex = 0; });
    ctx.section.querySelectorAll(".gd-filter [data-code]").forEach(box => { box.checked = false; });
    applyFilter();
  }

  // ---- the yellow info tooltip: drawn by the page under and left of the pointer, after a short rest ----
  let tipTarget = null;
  let tipTimer;

  // point: the pointer in viewport px, or null for keyboard focus (then the icon's bottom centre).
  function showTip(icon, point) {
    const page = ctx.root.querySelector(".pd-page");
    const tip = page.querySelector(".gd-tip");
    // Client coordinates are zoomed (#frame zoom); the page's own lengths are not.
    const box = page.getBoundingClientRect();
    const scale = box.width / page.offsetWidth;
    const target = icon.getBoundingClientRect();
    const [x, y] = point ? [point.x, point.y] : [target.left + target.width / 2, target.bottom];
    tip.textContent = icon.dataset.tip;
    tip.style.left = (x - box.left) / scale - 15 + "px";
    tip.style.top = (y - box.top) / scale + 7 + "px";
    tip.hidden = false;
    icon.setAttribute("aria-describedby", tip.id);
  }

  function hideTip() {
    clearTimeout(tipTimer);
    tipTarget?.removeAttribute("aria-describedby");
    tipTarget = null;
    const tip = ctx?.root.querySelector(".gd-tip");
    if (tip) tip.hidden = true;
  }

  function enterTip(event) {
    const icon = event.target.closest?.(".gd-info");
    if (!icon || icon === tipTarget) return;
    hideTip();
    tipTarget = icon;
    const point = event.type === "focusin" ? null : { x: event.clientX, y: event.clientY };
    if (DELAY) tipTimer = setTimeout(() => showTip(icon, point), DELAY.tip);
    else showTip(icon, point);
  }

  function leaveTip(event) {
    if (tipTarget && event.target.closest?.(".gd-info") === tipTarget && !tipTarget.contains(event.relatedTarget)) hideTip();
  }

  // ---- the embedded PDF viewer ----
  const ICONS = {
    menu: '<path d="M3 5h14M3 10h14M3 15h14"/>',
    minus: '<path d="M4 10h12"/>',
    plus: '<path d="M4 10h12M10 4v12"/>',
    fit: '<rect x="6" y="3" width="8" height="14" rx="1"/><path d="M8.5 7.5 10 6l1.5 1.5M8.5 12.5 10 14l1.5-1.5"/>',
    rotate: '<path d="M10.5 3.5A6.5 6.5 0 1 1 4.6 7.2"/><path d="M10.5 1v5l3-2.5z" fill="currentColor" stroke="none"/><path d="M5 9.5 7.5 12 5 14.5 2.5 12z"/>',
    draw: '<path d="M3 15c3-9 6-12 7-9s-5 9-2 10 5-8 7-6-1 5 2 5"/>',
    undo: '<path d="M7 5 3.5 8.5 7 12M3.5 8.5H12a4 4 0 0 1 0 8H9"/>',
    redo: '<path d="M13 5l3.5 3.5L13 12M16.5 8.5H8a4 4 0 0 0 0 8h3"/>',
    download: '<path d="M10 3v10M5.5 8.5 10 13l4.5-4.5M4 16.5h12"/>',
    print: '<path d="M6 7V3h8v4M6 14H3.5V8a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v6H14M6 11h8v6H6z"/>',
    more: '<circle cx="10" cy="4.5" r="1.3"/><circle cx="10" cy="10" r="1.3"/><circle cx="10" cy="15.5" r="1.3"/>',
  };
  // Toolbar controls at the centres measured on the recording (reference px from the toolbar's left edge; negative:
  // from its right edge, where Chrome keeps download, print and the menu).
  const at = x => x < 0 ? `right:${-x}px;transform:translate(50%,-50%)` : `left:${x}px`;
  const tool = (name, label, x, attributes = "") => `<button type="button" class="pv-tool" aria-label="${label}"
    style="${at(x)}"${attributes}><svg viewBox="0 0 20 20" aria-hidden="true">${ICONS[name]}</svg></button>`;
  const separators = [203.4, 296.1, 357.2, 390.9].map(x => `<i class="pv-sep" style="left:${x}px"></i>`).join("");

  // An invented one-page declaration, laid out with the line spacing of the scanned form in the recording (18m48s,
  // 18m53s): [class, html, distance from the previous line's centre in reference px]. Only an invented practice gets
  // invented personal details; for a real one (archive, reference) the form is left blank, never filled in its name.
  function sheet(row, subject) {
    const next = random(ctx.practice.key + "|" + row.type + "|" + subject.ndg);
    const pick = list => list[Math.floor(next() * list.length)];
    const invented = ctx.practice.role === "sintetica";
    const blank = length => "-".repeat(length);
    const town = invented ? pick(TOWNS) : blank(14);
    const born = invented ? shiftDate("01/01/2000", Math.floor(next() * 365 * 40)) : blank(10);
    const street = invented ? `${pick(STREETS)}, N. ${1 + Math.floor(next() * 180)}` : blank(22);
    const title = escapeText(row.type.replace(/^Mod\. [\d.]+ - /, ""));
    const holder = invented ? escapeText(subject.name.split(",")[0]) : blank(24);
    const date = escapeText(row.date);
    const specks = Array.from({ length: 70 }, () =>
      `<i style="left:${(next() * 100).toFixed(2)}%;top:${(next() * 100).toFixed(2)}%"></i>`).join("");
    const lines = [
      ["pv-title-line", title, 64.6],
      ["pv-sub", "(dichiarazione sostitutiva resa dal cliente per l'istruttoria)", 24],
      ["", `Il/La sottoscritto/a <u>${holder}</u>`, 22.7],
      ["pv-hint", '<span style="margin-left:100px">(cognome e nome)</span>', 22],
      ["", `nato/a a <u>${town}</u> il <u>${born}</u>`, 20.6],
      ["pv-hint", '<span style="margin-left:75px">(luogo)</span><span style="margin-left:88px">(data)</span>', 21.3],
      ["pv-just", "consapevole delle conseguenze previste per chi rende dichiarazioni non corrispondenti al vero o fa " +
        "uso di documenti non veritieri, sotto la propria responsabilità", 21.3],
      ["pv-center", "DICHIARA", 36.4],
      ["", `che la propria residenza anagrafica è a <u>${town}</u>`, 46.7],
      ["pv-hint", '<span style="margin-left:160px">(luogo)</span>', 21.3],
      ["", `in <u>${street}</u> e che quanto segue corrisponde al vero:`, 22],
      ["pv-item", `1)&ensp;i dati del documento «${title}» sono completi`, 45.3],
      ["pv-item", "2)&ensp;il documento è conforme all'originale in proprio possesso", 34.4],
      ["pv-item", "3)&ensp;la banca potrà verificare quanto dichiarato presso gli enti competenti", 22.7],
      ["pv-item", "4)&ensp;ogni variazione dei dati sarà comunicata tempestivamente", 34.4],
      ["pv-item", `5)&ensp;la dichiarazione è resa per la pratica n. <u>${escapeText(ctx.practice.number)}</u>`, 22.7],
      ["pv-sign", `Luogo e data <u>${town.replace(/ \(.*/, "")}, ${date}</u><span>Firma del dichiarante</span>`, 45.3],
      ["pv-sign", invented ? `<span class="pv-signature">${holder}</span>` : "", 30],
    ];
    // Every line box is 13.6 px tall (two for the justified paragraph); the margin makes up the rest of the distance
    // from the previous centre, or from the top of the page for the first line.
    let previous = 0;
    return `<article class="pv-sheet">${specks}${lines.map(([kind, html, gap]) => {
      const tall = kind === "pv-just" ? 26.6 : 13.6;
      const margin = gap - previous - (kind === "pv-just" ? 6.8 : tall / 2);
      previous = kind === "pv-just" ? 19.8 : tall / 2;
      return `<p class="${kind}" style="margin-top:${margin.toFixed(1)}px">${html}</p>`;
    }).join("")}</article>`;
  }

  function showViewer(row, subject) {
    const { section, practice } = ctx;
    const file = `${practice.number} - ${row.type}`;
    hideTip();
    section.dataset.phase = DELAY ? "viewer-blank" : "viewer";
    section.innerHTML = `<div class="pv-frame" role="region" aria-label="Visualizzatore PDF">
      <div class="pv-toolbar" role="toolbar" aria-label="${escapeText(file)}">
        ${tool("menu", "Menu", 22.7)}<span class="pv-title">${escapeText(file)}</span>
        <span class="pv-pages"><input aria-label="Numero di pagina" value="1"><span>/</span><span>1</span></span>
        ${tool("minus", "Riduci", 217.8)}<span class="pv-zoom">100%</span>${tool("plus", "Ingrandisci", 278.9)}
        ${tool("fit", "Adatta alla pagina", 314)}${tool("rotate", "Ruota", 337.3)}${tool("draw", "Disegna", 373.7)}
        ${tool("undo", "Annulla", 406.7, " disabled")}${tool("redo", "Ripeti", 430, " disabled")}${separators}
        ${tool("download", "Scarica", -74.2)}${tool("print", "Stampa", -48.1)}${tool("more", "Altre azioni", -21.3)}
      </div>
      <div class="pv-view" tabindex="0" aria-label="Pagina del documento"${DELAY ? " data-empty" : ""}>${sheet(row, subject)}</div>
      <label class="pv-scroll"><input type="range" min="0" max="100" value="0" aria-label="Scorrimento del documento"></label>
      <div class="pv-toast" role="status" hidden><i></i>Estrazione del testo dal PDF in corso...</div></div>
      <div class="gd-back"><button type="button" class="pd-bluebtn gd-indietro">Indietro</button></div>`;
    const view = section.querySelector(".pv-view");
    const range = section.querySelector(".pv-scroll input");
    range.oninput = () => { view.scrollTop = Number(range.value) * (view.scrollHeight - view.clientHeight) / 100; };
    view.onscroll = () => { range.value = 100 * view.scrollTop / Math.max(1, view.scrollHeight - view.clientHeight); };
    // Chrome draws the empty viewer first, then the page, then reads its text for a few seconds.
    later(DELAY?.blank, () => {
      delete view.dataset.empty;
      range.style.setProperty("--pv-thumb", Math.round(range.clientHeight * view.clientHeight / view.scrollHeight) + "px");
      if (!DELAY) return;
      section.dataset.phase = "viewer-text";
      section.querySelector(".pv-toast").hidden = false;
      later(DELAY.toast, () => {
        section.querySelector(".pv-toast").hidden = true;
        section.dataset.phase = "viewer";
      });
    });
  }

  function onClick(event) {
    const button = event.target.closest("button");
    if (!button || !ctx) return;
    const head = button.closest(".gd-head");
    if (head) {
      const open = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(open));
      head.nextElementSibling.hidden = !open;
      fitPage();
    } else if (button.dataset.doc) {
      const [s, g, r] = button.dataset.doc.split(".").map(Number);
      const subject = ctx.documents[s];
      request(DELAY?.file, () => showViewer(subject.groups[g].rows[r], subject));
    } else if (button.classList.contains("gd-indietro")) {
      request(DELAY?.page, showList);
    } else if (button.classList.contains("gd-apply")) {
      request(DELAY?.file, applyFilter);
    } else if (button.classList.contains("gd-reset")) {
      request(DELAY?.file, resetFilter);
    }
  }

  // Called by detail.js for every practice it renders; the page stays hidden until open().
  function render(section, practice, root) {
    close();
    ctx = { section, practice, root, documents: [] };
    section.addEventListener("click", onClick);
    for (const [type, handler] of [["mouseover", enterTip], ["focusin", enterTip], ["mouseout", leaveTip], ["focusout", leaveTip]])
      section.addEventListener(type, handler);
    // The tooltip belongs to the page, so it is placed in page coordinates and scrolls with it.
    root.querySelector(".pd-page").insertAdjacentHTML("beforeend", '<div class="gd-tip" role="tooltip" id="gd-tip" hidden></div>');
  }

  // The Funzioni link: a PEF 2.0 request whose answer replaces the work area (show() hides the other panels).
  function open(show) {
    if (!ctx) return;
    close();
    request(DELAY?.page, () => {
      ctx.documents = api.documentsOf(ctx.practice);
      show();
      showList();
    });
  }

  // Any other screen: drop pending requests, the wait and the tooltip, and give the page back its own height.
  function close() {
    timers.forEach(clearTimeout);
    timers = [];
    if (!ctx) return;
    hideTip();
    loading(false);
    ctx.root.querySelector(".pd-page")?.style.removeProperty("min-height");
  }

  const api = { render, open, close, documentsOf };
  window.BperDocs = api;
})();
