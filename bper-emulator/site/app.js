(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const frame = byId("frame");
  const original = byId("original");
  const screenSelect = byId("screen");
  const modeSelect = byId("mode");
  const practiceSelect = byId("practice");
  const home = byId("home-view");
  const search = byId("search-view");
  const list = byId("list-view");
  const detail = byId("detail-view");
  const veil = document.querySelector(".pm-veil");
  const app = byId("application");
  const cover = byId("shell-cover");
  const splash = byId("splash");
  const loading = window.BperLoading;
  const times = loading.TIMES;
  // The application tabs, by the view each one shows.
  const tabs = { home: byId("home-tab"), search: byId("search-tab"), list: byId("list-tab"), detail: byId("practice-tab") };
  const initial = new URL(location.href);
  const capture = initial.searchParams.get("capture") === "1";
  const consoleVisible = initial.searchParams.get("console") === "1" && !capture;
  // PEF 2.0 asks "pratica già in lavorazione" over its frame on some openings (video 18:12); what triggers it
  // is unknown, so only ?modal=1 asks it, at every opening of a practice.
  const askOnOpen = initial.searchParams.get("modal") === "1";
  // The capture window keeps the scale of the reference screenshots. Otherwise one reference pixel
  // is the 1.38 CSS px an operator sees at 100%: the references show a 1280 px desktop, 843.5 px
  // wide between their borders, at 110% zoom (1280 / 843.5 / 1.1).
  frame.style.setProperty("--zoom", capture ? "1" : "1.38");
  frame.dataset.scale = capture ? "capture" : "native";
  const offline = window.BperOffline;
  // The offline file also carries Scheda Privati, a separate application: its route replaces this page.
  if (offline?.schedaPage && location.hash.startsWith("#/schede/")) {
    addEventListener("DOMContentLoaded", () => {
      document.open();
      document.write(offline.schedaPage);
      document.close();
    }, { once: true });
    return;
  }
  const allSteps = Array.from({ length: 9 }, (_, i) => i + 1);
  let practices;
  let reference;
  let active;
  let mode = initial.searchParams.get("mode") === "reference" ? "reference" : "interactive";
  let step = 1;
  let csvObjectUrls = [];
  // A session started at the home page opens its tabs one by one and lists what Ricerca Pratica finds
  // (results). A direct link to a practice shows the tabs and the one-row list of the reference screenshots.
  let view = "list";
  let opened = new Set(["search", "list"]);
  let results = null;
  let framed = null;
  let dialogPending = false;
  // The shell's loading phase (loading.css reads it on #application) and how to stop the practice opening.
  let phase = null;
  let stopOpening = () => {};
  let openedDialog = false;
  const coverPhases = ["blank", "partial", "washed", "settle", "quiet"];

  function readStep() {
    return /^#[1-9]$/.test(location.hash) ? Number(location.hash.slice(1)) : 1;
  }

  function buildUrl() {
    const url = new URL(location.href);
    if (active) url.searchParams.set("practice", active.key);
    else url.searchParams.delete("practice");
    if (mode === "reference") url.searchParams.set("mode", "reference");
    else url.searchParams.delete("mode");
    url.hash = view === "search" ? "ricerca" : String(step);
    return url;
  }

  function syncUrl() {
    const url = buildUrl();
    if (url.href === location.href) return;
    // File URLs support fragment changes in history but require navigation for query changes.
    if (url.protocol === "file:" && url.search !== location.search) location.replace(url.href);
    else history.replaceState(null, "", url.href);
  }

  async function jsonAt(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error("Dati non disponibili: " + path);
    return response.json();
  }

  // Truth per screen (dati.csv) and one row per field of the practice (practice-truth.csv).
  function setCsvLink() {
    csvObjectUrls.forEach(url => URL.revokeObjectURL(url));
    csvObjectUrls = [];
    for (const [id, table, endpoint] of [["truth-download", "truth", "/api/truth/"],
                                         ["practice-truth-download", "practiceTruth", "/api/truth-practice/"]]) {
      const link = byId(id);
      link.hidden = !active || active === reference;
      link.removeAttribute("href");
      if (link.hidden) continue;
      if (offline) {
        const url = URL.createObjectURL(new Blob(["﻿", offline[table][active.key]], { type: "text/csv;charset=utf-8" }));
        csvObjectUrls.push(url);
        link.href = url;
      } else {
        link.href = endpoint + encodeURIComponent(active.key) + ".csv";
      }
    }
  }

  function showView(name) {
    view = name;
    home.hidden = name !== "home";
    search.hidden = name !== "search";
    list.hidden = name !== "list";
    detail.hidden = name !== "detail";
    for (const [key, tab] of Object.entries(tabs)) {
      if (key !== "home") tab.hidden = !opened.has(key);
      tab.setAttribute("aria-current", key === name ? "page" : "false");
    }
    // The dialog and a practice still loading belong to the PEF 2.0 tab: they wait there while another tab is shown.
    veil.hidden = !(name === "detail" && dialogPending);
    cover.hidden = !(name === "detail" && coverPhases.includes(phase));
    if (name === "home" || name === "search") {
      original.hidden = true;
      frame.classList.remove("reference");
    }
  }

  function setPhase(name) {
    phase = name;
    if (name) app.dataset.loading = name;
    else delete app.dataset.loading;
    splash.hidden = name !== "boot" && name !== "splash";
    cover.hidden = !(view === "detail" && coverPhases.includes(name));
  }

  const wait = ms => new Promise(resolve => loading.sequence([[ms, resolve]]));

  // Before its images arrive the PEF 2.0 page draws without its navy bars and blue buttons (frame 02m01s): for that
  // phase every element with a dark or image background loses it, and so do the icons drawn before or after one.
  function bareDetail(on) {
    if (!on) {
      detail.querySelectorAll(".ld-bare, .ld-bare-icons").forEach(node => node.classList.remove("ld-bare", "ld-bare-icons"));
      return;
    }
    for (const node of detail.querySelectorAll("*")) {
      const style = getComputedStyle(node);
      const [r, g, b, a = 1] = style.backgroundColor.match(/[\d.]+/g).map(Number);
      if (style.backgroundImage !== "none" || (a > 0.5 && 0.299 * r + 0.587 * g + 0.114 * b < 110)) node.classList.add("ld-bare");
      if (["::before", "::after"].some(part => getComputedStyle(node, part).backgroundImage !== "none")) node.classList.add("ld-bare-icons");
    }
  }

  // A practice opened from the row menu (spec 7; main recording 01:55.4-02:02.8): its tab at once over a blank area
  // with the ring, the page half drawn and washed out, washed out, then whole. With the "già in lavorazione" dialog
  // (18:12) only a short blank comes before the dialog; the rest follows its buttons.
  function openFromMenu(show) {
    const clicked = performance.now();
    stopLoading();
    show();
    if (!loading.enabled || view !== "detail") return;
    // The phases are timed from the click: building the page, behind the blank, takes part of the blank's time.
    const built = performance.now() - clicked;
    if (dialogPending) {
      openedDialog = true;
      stopOpening = loading.sequence([[0, () => setPhase("blank")], [Math.max(0, times.dialogBlank - built), () => {
        setPhase(null);
        veil.classList.add("ld-fade");
      }]]);
      return;
    }
    stopOpening = loading.sequence([
      [0, () => setPhase("blank")],
      [Math.max(0, times.blank - built), () => { bareDetail(true); setPhase("partial"); }],
      [times.partial, () => { bareDetail(false); setPhase("washed"); }],
      [times.washed, () => setPhase("settle")],
      [times.settle, () => setPhase(null)],
    ]);
  }

  // After the dialog of an opening from the row menu (18:19): a blank without the ring, then the whole page. The
  // dialog of a direct link goes at once, like the rest of that link.
  function closeDialog() {
    dialogPending = false;
    veil.hidden = true;
    veil.classList.remove("ld-fade");
    const quiet = openedDialog && view === "detail";
    openedDialog = false;
    if (!quiet) return;
    stopOpening();
    stopOpening = loading.sequence([[0, () => setPhase("quiet")], [times.confirmBlank, () => setPhase(null)]]);
  }

  function updateConsole() {
    const available = active?.availableSteps || allSteps;
    screenSelect.value = String(step);
    for (const option of screenSelect.options) option.disabled = !available.includes(Number(option.value));
    byId("previous-screen").disabled = step === available[0];
    byId("next-screen").disabled = step === available.at(-1);
  }

  // A state of the reference screenshots, from a direct link, a key, the console or the PEF 2.0 page itself.
  function showStep(requested, syncView = true) {
    if (!active) {
      if (requested !== 1) openPractice(practices[0], requested);
      else startSession("home");
      return;
    }
    const available = active.availableSteps || allSteps;
    // A direct link to a missing tooltip opens its underlying table; a page the practice lacks, its first state.
    const fallback = requested === 3 ? 2 : 5;
    step = available.includes(requested) ? requested : available.includes(fallback) ? fallback : available[0];
    const isList = step <= 3;
    // A jump to a list state shows the one-row list of the references again.
    if (results && isList && syncView) {
      results = null;
      renderList();
    }
    if (!results) opened = new Set(isList ? ["search", "list"] : ["search", "list", "detail"]);
    if (!isList && (tabs.detail.hidden || framed !== active)) {
      framed = active;
      dialogPending = askOnOpen;
    }
    if (!isList) opened.add("detail");
    showView(isList ? "list" : "detail");
    if (syncView) (isList ? window.BperList : window.BperDetail).show(step);
    updateConsole();
    original.hidden = mode !== "reference";
    frame.classList.toggle("reference", !original.hidden);
    if (!original.hidden) {
      const src = offline ? offline.screens[step] : "/reference/" + step + ".png";
      if (original.getAttribute("src") !== src) original.src = src;
    }
    syncUrl();
  }

  // The header, the console and the PEF 2.0 page follow the chosen practice; the list does not.
  function selectPractice(profile) {
    active = profile;
    if (!profile || profile !== reference) mode = "interactive";
    practiceSelect.value = profile?.key || "";
    modeSelect.value = mode;
    modeSelect.disabled = !reference || profile !== reference;
    byId("open-scheda").disabled = !profile?.scheda;
    const operator = profile || practices[0];
    byId("operator-name").textContent = operator.operatorName;
    byId("operator-codes").textContent = [operator.operatorId, operator.abi.padStart(5, "0"), operator.officeCode || operator.assignee].join("　");
    setCsvLink();
    if (!profile) {
      detail.replaceChildren();
      return;
    }
    byId("practice-caption").textContent = "PEF 2.0 - Pratica: " + profile.number;
    window.BperDetail.render(detail, profile, {
      onState: n => { if (active === profile && step >= 4) showStep(n, false); },
    });
  }

  function renderList() {
    const profile = active;
    // Ignore delayed blur/scroll from a panel which navigation just closed.
    window.BperList.render(list, profile, {
      openPractice: () => openFromMenu(() => showStep(4)),
      onState: n => { if (active === profile && step <= 3 && !results) showStep(n, false); },
    });
  }

  // Developer paths (a direct link, the console, the keys 1-9) open at once: they also drop an opening still under
  // way, and a PEF 2.0 request still waiting, whose answer would otherwise move the page they chose.
  function stopLoading() {
    stopOpening();
    loading.stop(detail);
    openedDialog = false;
    if (coverPhases.includes(phase)) {
      bareDetail(false);
      setPhase(null);
    }
  }

  function openPractice(profile, requested = 4) {
    stopLoading();
    results = null;
    selectPractice(profile);
    if (!profile) {
      startSession("home");
      return;
    }
    renderList();
    showStep(requested);
  }

  // The application as it opens: the home tab only (video 01:35), or the search form of a direct link.
  function startSession(name) {
    stopLoading();
    selectPractice(null);
    results = null;
    framed = null;
    dialogPending = false;
    opened = new Set(name === "search" ? ["search"] : []);
    list.replaceChildren();
    step = 1;
    showView(name);
    updateConsole();
    syncUrl();
  }

  function showSearch() {
    opened.add("search");
    showView("search");
    syncUrl();
  }

  function showResults(found, filters) {
    results = found;
    opened.add("list");
    window.BperList.render(list, null, {
      results: found, filters, openPractice: p => openFromMenu(() => openFromResults(p)), onState: () => {},
    });
    showList();
  }

  function showList() {
    step = 1;
    showView("list");
    updateConsole();
    syncUrl();
  }

  function openFromResults(profile) {
    if (profile !== active) selectPractice(profile);
    showStep(4);
  }

  function adjacent(direction) {
    const available = active?.availableSteps || allSteps;
    const next = available[available.indexOf(step) + direction];
    if (next) showStep(next);
  }

  async function start() {
    if (consoleVisible) {
      document.body.classList.add("console");
      byId("controls").hidden = false;
      document.title = "Banco di prova · Nuova PEF";
    }
    // The application as it starts (main recording 01:32.75-01:33.5, MOL 01 01:12.4-01:13.25): a bare white page with
    // a small ring, the logo over it, then the home faded while it loads. A direct link opens at once.
    const splashed = loading.enabled && !initial.searchParams.get("practice") && mode !== "reference" &&
      readStep() === 1 && location.hash !== "#ricerca"
      ? (setPhase("boot"), wait(times.boot).then(() => { setPhase("splash"); return wait(times.splash); }))
      : null;
    const catalog = offline || await jsonAt("/api/practices.json");
    practices = catalog.practices;
    if (!practices?.length) throw new Error("Nessuna pratica nel database.");
    const profiles = new Map(practices.map(p => [p.key, p]));
    // Real practices carry their archive role, so test material is never taken for synthetic data.
    for (const p of practices) {
      const role = p.role && p.role !== "sintetica" ? " [" + p.role + "]" : "";
      practiceSelect.add(new Option(p.name + " · " + p.number + role, p.key));
    }
    if (catalog.hasReference) {
      reference = offline ? offline.practice : await jsonAt("/reference/practice.json");
      reference.key = "reference";
      reference.availableSteps = allSteps;
      profiles.set(reference.key, reference);
      practiceSelect.add(new Option("Pratica di riferimento", reference.key));
      modeSelect.hidden = false;
      document.querySelector('label[for="mode"]').hidden = false;
    }
    const key = initial.searchParams.get("practice") || (mode === "reference" ? "reference" : "");
    if (key && !profiles.has(key)) throw new Error("La pratica richiesta non è presente in questo catalogo.");
    window.BperHome.render(home, { onSearch: showSearch });
    window.BperSearch.render(search, reference ? [...practices, reference] : practices, { onSubmit: showResults });
    // A developer convenience, not part of the application: find a practice of the catalogue by NDG, name or number.
    if (consoleVisible) window.BperList.directory(byId("catalogue"), practices, { openPractice: p => openPractice(p) });
    const requested = readStep();
    const profile = profiles.get(key) || (requested > 1 ? practices[0] : null);
    if (profile) openPractice(profile, requested);
    else startSession(location.hash === "#ricerca" ? "search" : "home");
    if (profile && location.hash === "#ricerca") showSearch();

    screenSelect.onchange = () => { stopLoading(); showStep(Number(screenSelect.value)); };
    byId("previous-screen").onclick = () => { stopLoading(); adjacent(-1); };
    byId("next-screen").onclick = () => { stopLoading(); adjacent(1); };
    tabs.home.onclick = () => { showView("home"); syncUrl(); };
    tabs.search.onclick = showSearch;
    tabs.list.onclick = () => (results ? showList() : showStep(1));
    // Its X closes the practice tab and shows the list, the searched one if any (MOL 06 15:36, MOL 03 37:56); an
    // opening still under way stops with it.
    tabs.detail.onclick = event => {
      if (!event.target.closest("i")) return showStep(4);
      stopLoading();
      opened.delete("detail");
      framed = null;
      if (results) showList();
      else showStep(1);
    };
    for (const button of veil.querySelectorAll("button")) {
      // What Annulla does in the real application was not seen: both buttons let the page show.
      button.onclick = closeDialog;
    }
    practiceSelect.onchange = () => openPractice(profiles.get(practiceSelect.value), practiceSelect.value ? step : 1);
    modeSelect.onchange = () => { mode = modeSelect.value; showStep(step); };
    byId("open-capture").onclick = () => {
      const url = buildUrl();
      url.searchParams.delete("console");
      url.searchParams.set("capture", "1");
      const popup = window.open(url.href, "nuova-pef-cattura",
        "popup,width=842,height=617,resizable=yes");
      if (popup) popup.focus();
      else location.assign(url.href);
    };
    // Scheda Privati is a separate application; how the real PEF links to it is unknown, so only the
    // console opens it, at the size of its reference screenshots (1903 px page plus scrollbar).
    byId("open-scheda").onclick = () => {
      if (!active?.scheda) return;
      const url = offline ? new URL(location.pathname, location.href) : new URL("/schede/SchedaPrivati/", location.href);
      // The page's customer: in a joint practice one holder, not the practice's own NDG.
      url.hash = "/schede/" + encodeURIComponent(active.scheda.ndg) + "/" + encodeURIComponent(active.scheda.schedaId);
      // ASSUMPTION, never recorded (spec 17): Scheda Privati is a BSpace procedure, and a BSpace procedure (PRICELAB,
      // MOL 01 09:13-09:17) opens on a blank about:blank page titled "Caricamento in corso..." for about 4 s first.
      const popup = window.open(loading.enabled ? "" : url.href, "scheda-privati", "popup,width=1920,height=945,resizable=yes");
      if (!popup) {
        location.assign(url.href);
        return;
      }
      popup.focus();
      if (!loading.enabled) return;
      try {
        popup.document.open();
        popup.document.write('<!doctype html><title>Caricamento in corso...</title><body style="margin:0;background:#fff">');
      } catch {
        // A window of the offline file already on the Scheda is of another origin: it is simply sent there.
      }
      setTimeout(() => popup.location.replace(url.href), times.scheda);
    };
    window.addEventListener("hashchange", () => (location.hash === "#ricerca" ? showSearch() : showStep(readStep())));
    document.addEventListener("keydown", event => {
      if (event.ctrlKey || event.altKey || event.metaKey) return;
      if (event.key === "F2") {
        event.preventDefault();
        const url = buildUrl();
        url.searchParams.delete("capture");
        if (consoleVisible) url.searchParams.delete("console");
        else url.searchParams.set("console", "1");
        location.assign(url.href);
        return;
      }
      if (event.target.closest("select,input,textarea")) return;
      if (/^[1-9]$/.test(event.key)) {
        event.preventDefault();
        stopLoading();
        showStep(Number(event.key));
      }
    });
    if (splashed) {
      await splashed;
      setPhase("home");
      await wait(times.home);
      setPhase(null);
    }
    frame.dataset.ready = "true";
  }

  start().catch(error => {
    setPhase(null);
    const message = byId("error-message");
    message.textContent = "Impossibile aprire il simulatore. " + error.message;
    message.hidden = false;
  });
})();
