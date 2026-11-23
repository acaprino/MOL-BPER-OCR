/* PEF 2.0 pages and states of the MOL recordings that the reference screenshots lack (spec 18.2, frames C18_*):
   Recupero Segnalazioni, Note Delibere Precedenti with its "Recupero Fidi e Garanzie in corso" notice, the lower
   blocks of Gestione Fidi e Garanzie, the Avvertenza of the navigator's X and the logout page after it, and the
   navigator of a practice opened in visualizzazione. detail.js hosts them and owns their navigation; this file draws
   them. What they show is invented, derived from the practice like docs.js: a hash of its key picks it, so a practice
   always shows the same. A real practice (archive, reference) gets the labels and nothing invented. Lengths are
   reference px, like detail.css. No element carries data-field: none of these pages shows one of the 45 fields. */
(() => {
  "use strict";

  // Milliseconds at native scale; nothing waits with ?capture=1 or ?loading=off (loading.js).
  const TIMES = {
    alerts: 16000,  // Recupero Segnalazioni: 14-18 s of ring first (MOL 01 02:42-03:00, MOL 04 01:04-01:20, MOL 11 02:03-02:22)
    review: 7500,   // Presa Visione or another subject: the page comes back on it (MOL 11 02:24-02:32)
    page: 1500,     // the other requests of these pages, "1-2 s after each inner tab/navigator click" (spec 9)
    notice: 2000,   // Note Delibere Precedenti alone, then "Recupero Fidi e Garanzie in corso" (spec 18.5, 02:45-02:47)
    credit: 5000,   // the notice before Gestione Fidi e Garanzie (spec 18.5, 02:47-02:52)
    exit: 1500,     // Conferma of Avvertenza: the ring over the dialog, then the logout page (MOL 03 37:52-37:54)
  };
  const REGIONS = ["EMILIA", "LOMBARDIA", "TOSCANA", "VENETO", "CAMPANIA", "SICILIA", "PUGLIA", "LAZIO", "CALABRIA",
    "SARDEGNA"];

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  // FNV-1a of the seed, then mulberry32, as in docs.js: the same practice always draws the same.
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

  const invented = practice => practice.role === "sintetica";
  // Thousands with a dot, as in the frames: it-IT in Intl leaves four digits ungrouped.
  const amount = value => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const subjectsOf = practice => practice.subjects?.length ? practice.subjects
    : [{ ndg: practice.ndg, name: practice.name, role: "Richiedente" }];

  // ---- the practice's mode and navigator (spec 18.2 Layouts 1; the archive's calibration screenshots) ----
  // A real practice opens as the archive's screenshots show it: worked in Verifica Preliminare (the reference practice),
  // in visualizzazione past it (13 practices of 13; with the reference, 14 of 14 fit). An invented one is worked unless
  // ?visualizzazione=1 (detail.js).
  // shortcut: the mode is read from the phase alone, the archive records no mode; read a profile field once it does.
  const viewOnlyOf = practice => !invented(practice) && practice.phase !== "VEP";

  // {groups, phase, returned, body, request, done, until}: the groups listed, the practice's phase (the current group),
  // whether Istruttoria starts with Note alla Restituzione, the deliberating body under Delibera, whether the practice
  // passed through Richiesta (that group, Modulistica and the extra buttons of Gestione Fidi e Garanzie come together),
  // whether every step is done, and the Istruttoria item the list stops at. Worked, the navigator of the reference
  // screenshots. Only an invented practice passes through Richiesta, drawn from its key.
  // shortcut: a real practice never shows the Richiesta group, the archive does not record it (3 calibration practices
  // of 13 have it); give the profile a field for it once the archive records it.
  function navigatorOf(practice, viewOnly) {
    const plain = { groups: ["VEP", "IST", "PRO", "PAR", "DEL"], phase: null, returned: false, body: "", request: false,
      done: false, until: null };
    if (!viewOnly) return plain;
    const phase = ["VEP", "IST", "PRO", "DEL"].includes(practice.phase) ? practice.phase : "IST";
    if (!invented(practice)) {
      // Approved: every step ticked. Istruttoria (or unknown): the steps up to Gestione Fidi e Garanzie, ticked, and no
      // later group. Proposta: Istruttoria complete and no Parere (4, 7 and 1 practices of the calibration fold).
      if (practice.state === "APP") return { ...plain, done: true };
      if (phase === "IST") return { ...plain, groups: ["VEP", "IST"], done: true, until: "fidi" };
      return { ...plain, groups: phase === "PRO" ? ["VEP", "IST", "PRO", "DEL"] : plain.groups, phase };
    }
    const next = random(practice.key + "|navigatore");
    const [request, parere, returned, region] = [next() < 0.5, next() < 0.6, next() < 0.3,
      REGIONS[Math.floor(next() * REGIONS.length)]];
    const withRequest = groups => request ? [groups[0], "RIC", ...groups.slice(1)] : groups;
    const body = `UFF.AN.E<br>CONC.CR.${region}-...`;
    const groups = withRequest(["VEP", "IST", "PRO", ...(parere ? ["PAR"] : []), "DEL"]);
    // Approved or abandoned like the archive's practices (generated-set-02): every step done, or Istruttoria up to
    // Gestione Fidi e Garanzie and no later group.
    if (practice.state === "APP") return { ...plain, groups, returned, body, request, done: true };
    if (practice.state === "ABB") {
      return { ...plain, groups: withRequest(["VEP", "IST"]), request, done: true, until: "fidi" };
    }
    return {
      groups,
      phase,
      returned: returned && phase !== "VEP",
      body: phase === "PRO" || phase === "DEL" ? body : "",
      request, done: false, until: null,
    };
  }

  // ---- the header of a practice opened in visualizzazione (the archive's calibration screenshots) ----
  // {instructor, proposer, legalForm, segment}: Istruttore and Proponente after Filiale, the Proponente from Istruttoria
  // on (6 practices of 7), the Istruttore past it (5 of 5, a name or a 6-digit id); the legal form of a joint account;
  // the behavioural segment (13 of 13). An invented practice gets them from its key, a real one only the legal form its
  // name implies. Worked, the header of the reference screenshots.
  const STAFF = ["ROSSETTI MARCO", "BELLINI ANNA MARIA", "CARUSO GIANFRANCO EMILIO", "DE ANGELIS PAOLA", "FONTANA LUCA",
    "MARCHETTI ELISA BEATRICE", "GALLO STEFANO", "VITALE FRANCESCA", "ORLANDI PIER GIORGIO", "SERRA GIULIA"];
  const SEGMENTS = ["FARES ENTITA' RESIDUALE FAMILY", "FAIMP FAMILY A VALORE FOCUS IMPIEGHI", "FACOR FAMILY CORE"];
  const JOINT = "CO COINTESTAZIONE FRA PERSONE FISICHE (PF)";

  function headerOf(practice, viewOnly) {
    const legalForm = viewOnly && String(practice.name).includes(",") ? JOINT : "";
    // shortcut: a real practice shows no names nor segment, valori.csv has none and the profile format no field for
    // them; add them to both once the archive records them.
    if (!viewOnly || !invented(practice)) return { instructor: "", proposer: "", legalForm, segment: "" };
    const next = random(practice.key + "|intestazione");
    const pick = list => list[Math.floor(next() * list.length)];
    const [proposed, numbered, proposer, instructor, id, segment] = [next() < 0.86, next() < 0.6, pick(STAFF), pick(STAFF),
      String(800000 + Math.floor(next() * 100000)), pick(SEGMENTS)];
    const past = ["PRO", "DEL"].includes(practice.phase) || practice.state === "APP";
    return {
      instructor: past ? (numbered ? id : instructor) : "",
      proposer: past || (practice.phase === "IST" && proposed) ? proposer : "",
      legalForm, segment,
    };
  }

  // ---- Recupero Segnalazioni (spec 18.2 Layouts 2; MOL 11 02:23, MOL 04 01:21) ----
  // [label, link]: underlined labels are links. Nuovo NDG shows only for a customer new to the bank.
  const INTERNAL = [["Rating Ufficiale", true], ["Rating Andamentale", true], ["RDB", true],
    ["Verifiche Precedenti Archiviate", false], ["Pratiche in Corso", true], ["Nuovo NDG", false], ["Dati Anagrafici", true]];
  const EXTERNAL = [["Protesti", false], ["Pregiudizievoli", false], ["Procedure Concorsuali", false],
    ["Dossier CERVED", true], ["Sofferenze CR", false], ["Segnalazioni Status Sofferenze da Sistema", false]];
  const POLICY = ["Settore di attività economica ATECO:", "SOW MAX", "SOW CR", "- Quota Medio Termine su Totale Sistema"];

  // {internal: [{label, link, text, dot, side}], external: [{label, link, text, dot}], strategy, policy: [[label, value]],
  //  granted: [[bank, group] accordato, [bank, group] utilizzato]}. dot: "green", "red", "grey", "new" (the red "!")
  // or "". A joint account reads like MOL 04 (texts instead of dots, more policy rows), a person like MOL 11.
  function alertsOf(practice, subject) {
    if (!invented(practice)) {
      return {
        internal: INTERNAL.filter(([label]) => label !== "Nuovo NDG")
          .map(([label, link]) => ({ label, link, text: "", dot: "", side: "" })),
        external: EXTERNAL.map(([label, link]) => ({ label, link, text: "", dot: "" })),
        strategy: "", policy: [], granted: [["", ""], ["", ""]],
      };
    }
    const next = random(`${practice.key}|${subject.ndg}|segnalazioni`);
    const joint = String(subject.name).includes(",");
    const fresh = next() < 0.25;
    const internal = {
      "Rating Ufficiale": { text: "Non Disponibile" }, "Rating Andamentale": { text: "Non Disponibile" },
      "RDB": { dot: next() < 0.6 ? "green" : "grey" }, "Verifiche Precedenti Archiviate": { dot: "green" },
      "Pratiche in Corso": { side: next() < 0.5 ? "Sì" : "NO" },
      "Nuovo NDG": { dot: "new", side: shiftDate(practice.created, 3 + Math.floor(next() * 20)) },
      "Dati Anagrafici": { dot: joint ? "grey" : next() < 0.3 ? "red" : "green" },
    };
    const granted = next() < 0.4 ? 0 : 1000 * (1 + Math.floor(next() * 30));
    const used = next() < 0.5 ? 0 : granted;
    return {
      internal: INTERNAL.filter(([label]) => label !== "Nuovo NDG" || fresh)
        .map(([label, link]) => ({ label, link, text: "", dot: "", side: "", ...internal[label] })),
      external: EXTERNAL.map(([label, link], i) => joint
        ? { label, link, text: i === 4 ? "Non Disponibile" : i === 5 ? "" : "Non Calcolabile", dot: i === 5 ? "green" : "" }
        : { label, link, text: "", dot: link ? "" : "green" }),
      strategy: "Non calcolabile (mancanza di rating)",
      policy: joint ? POLICY.map((label, i) => [label, ["-", "N/A", "NC", "NC"][i]]) : [],
      granted: [[amount(granted), "0"], [amount(used), "0"]],
    };
  }

  const dot = kind => kind === "new" ? '<b class="rs-new" aria-label="Nuovo">!</b>'
    : kind ? `<i class="pd-dot pd-dot-${kind}" aria-label="${{ green: "Regolare", red: "Anomalia", grey: "Non verificato" }[kind]}"></i>` : "";
  const label = ([text, link]) => link ? `<a href="#" class="rs-link">${escapeText(text)}</a>` : escapeText(text);
  const box = (className, title, body) => `<section class="rs-box ${className}"><h3 class="pd-bar">${title}</h3>${body}</section>`;

  // The page for the subject at `index` (detail.js keeps the index); `data` is alertsOf() of that subject.
  function alertsPage(practice, index, data = api.alertsOf(practice, subjectsOf(practice)[index])) {
    const options = subjectsOf(practice).map((s, i) =>
      `<option${i === index ? " selected" : ""}>${escapeText(`${s.ndg} - ${s.name} - ${s.role}`)}</option>`).join("");
    const internal = data.internal.map(row => `<tr><td>${label([row.label, row.link])}</td>
      <td data-value>${escapeText(row.text)}${dot(row.dot)}</td><td data-value>${escapeText(row.side)}</td></tr>`).join("");
    const external = data.external.map(row => `<tr><td>${label([row.label, row.link])}</td>
      <td data-value>${escapeText(row.text)}${dot(row.dot)}</td></tr>`).join("");
    const policy = [["Strategia", data.strategy, "rs-strategy"], ...data.policy].map(([name, value, className = ""]) =>
      `<tr><td>${escapeText(name)}</td><td data-value class="${className}">${escapeText(value)}</td></tr>`).join("");
    const [[bank, group], [usedBank, usedGroup]] = data.granted;
    return `<div class="rs-subject"><label for="rs-soggetto">Soggetto corrente:</label>
      <span class="rs-select"><i class="rs-no" aria-hidden="true"></i><select id="rs-soggetto">${options}</select></span></div>
      <div class="pd-date">Situazione al ${escapeText(practice.created)}<span class="pd-bluebtn" role="button">Refresh</span></div>
      <div class="rs-columns"><div>
      ${box("rs-internal", "Banche Dati Interne", `<table class="rs-table">${internal}</table>`)}
      ${box("rs-policy", 'Politiche Creditizie<i class="pd-help" aria-label="Aiuto">?</i>', `<table class="rs-table">${policy}</table>`)}
      </div><div>
      ${box("rs-external", "Banche Dati Esterne", `<table class="rs-table">${external}</table>`)}
      ${box("rs-granted", 'Accordato/Utilizzato<a href="#" class="rs-sow">SOW</a>', `<table class="rs-table">
        <tr><th></th><th scope="col">Banca</th><th scope="col">Altre Banche del Gruppo</th></tr>
        <tr><td>Accordato</td><td data-value>${escapeText(bank)}</td><td data-value>${escapeText(group)}</td></tr>
        <tr><td>Utilizzato</td><td data-value>${escapeText(usedBank)}</td><td data-value>${escapeText(usedGroup)}</td></tr></table>`)}
      <div class="pd-actions"><button type="button" class="pd-bluebtn" data-rs="review">Presa Visione &gt;</button></div>
      </div></div>
      <div class="rs-note"><h3 class="pd-bar pd-fold">Nota alla verifica preliminare</h3><div class="rs-note-body"></div></div>
      <div class="pd-actions"><button type="button" class="pd-bluebtn" data-rs="next">Avvia Step Succ. &gt;</button></div>`;
  }

  // ---- Note Delibere Precedenti (spec 15.5 and 18.2 Layouts 4; MOL 04 02:13, main recording 02:52) ----
  // [{ndg, date, body, number, amount}], newest first: none for most practices and for every real one.
  function resolutionsOf(practice) {
    if (!invented(practice)) return [];
    const next = random(practice.key + "|delibere");
    const count = [0, 0, 0, 1, 2, 3][Math.floor(next() * 6)];
    const days = Array.from({ length: count }, () => 5 + Math.floor(next() * 340)).sort((a, b) => a - b);
    return days.map(day => ({
      ndg: practice.ndg, date: shiftDate(practice.created, day), body: practice.branchName,
      number: "47" + String(Math.floor(next() * 1e6)).padStart(6, "0"),
      amount: next() < 0.3 ? "0" : amount(500 * (1 + Math.floor(next() * 60))),
    }));
  }

  function resolutionsPage(practice, rows = api.resolutionsOf(practice)) {
    const list = rows.length
      ? `<table class="pd-table nd-table" aria-label="Elenco delibere"><colgroup>
          ${[100, 120, 79, 124, 107, 62].map(w => `<col style="width:${w}px">`).join("")}</colgroup>
          <thead><tr>${["NDG", "Data Delibera", "Deliberante", "N° Pratica", "Importo", ""]
            .map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead>
          <tbody>${rows.map(r => `<tr><td>${escapeText(r.ndg)}</td><td>${escapeText(r.date)}</td><td>${escapeText(r.body)}</td>
            <td>${escapeText(r.number)}</td><td>${escapeText(r.amount)}</td><td><i class="nd-zoom" aria-label="Dettaglio"></i></td></tr>`)
            .join("")}</tbody></table>`
      : '<p class="nd-empty">Elenco delibere precedenti non presente</p>';
    return `<div class="pd-date">Dati aggiornati al ${escapeText(practice.created)}<span class="pd-bluebtn" role="button">Refresh</span></div>
      <h3 class="pd-bar nd-bar">Elenco delibere ultimi 12 mesi<em>24 mesi</em></h3>${list}
      <div class="pd-actions"><button type="button" class="pd-bluebtn" data-nd="next">Avvia Step Succ. &gt;</button></div>`;
  }

  // Over the frame while Gestione Fidi e Garanzie loads after Note Delibere Precedenti (main recording 02:52).
  const NOTICE = '<div class="nd-notice" role="status"><i class="nd-hourglass" aria-hidden="true"></i>Recupero Fidi e Garanzie in corso</div>';

  // ---- Gestione Fidi e Garanzie, under Strategie Politiche Creditizie (spec 18.2 Layouts 3; MOL 02 01:49, MOL 05 06:53) ----
  // Both recorded practices show "€ 0"; a real practice shows no amount. In visualizzazione the notes have no Salva.
  function lowerBlocks(practice, viewOnly) {
    const zero = invented(practice) ? "€ 0" : "";
    return `<div class="pd-lower">
      <section class="pd-decalage"><h3 class="pd-bar pd-fold">Decalage<i class="pd-help" aria-label="Aiuto">?</i></h3>
      <table aria-label="Decalage"><tr><td>Effettivo a -12 mesi</td><td>${zero}</td></tr><tr><td>Teorico a +12 mesi</td><td>${zero}</td></tr></table></section>
      <section class="pd-policy-notes"><h3 class="pd-bar pd-fold"><span>Note alle Politiche Creditizie</span>${viewOnly ? ""
        : '<button type="button" class="pd-save">Salva<i aria-hidden="true"></i></button>'}</h3>
      <textarea aria-label="Note alle Politiche Creditizie"${viewOnly ? " readonly" : ""}></textarea></section></div>`;
  }

  // ---- the X of the navigator (spec 18.5 row 5; MOL 06 08:22 and 15:33, MOL 03 37:53) ----
  const ALERT = `<div class="pd-alert" role="alertdialog" aria-modal="true" aria-labelledby="pd-alert-title" aria-describedby="pd-alert-message">
    <div class="pd-alert-title" id="pd-alert-title">Avvertenza</div>
    <div class="pd-alert-message" id="pd-alert-message">PDCGPC0012A :Uscire dalla pratica?</div>
    <div class="pd-alert-buttons"><button type="button" class="pd-bluebtn" data-alert="cancel">Annulla</button><button type="button" class="pd-bluebtn" data-alert="confirm">Conferma</button></div></div>`;
  // After Conferma the frame holds a bare page (MOL 06 15:34, read at 480 x 270); the practice tab stays open.
  const LOGOUT = '<div class="pd-logout" data-panel="logout" hidden><p>Pagina logout PEF<br>Si prega di chiudere il tab per poter procedere con la lavorazione/visualizzazione di altre PEF 2.0</p></div>';

  const api = { TIMES, subjectsOf, viewOnlyOf, navigatorOf, headerOf, alertsOf, alertsPage, resolutionsOf,
    resolutionsPage, lowerBlocks, NOTICE, ALERT, LOGOUT };
  window.BperPefExtra = api;
})();
