(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const frame = byId("frame");
  const stage = byId("stage");
  const original = byId("original");
  const screenSelect = byId("screen");
  const modeSelect = byId("mode");
  const practiceSelect = byId("practice");
  const list = byId("list-view");
  const detail = byId("detail-view");
  const initial = new URL(location.href);
  const consoleVisible = initial.searchParams.get("console") === "1" && initial.searchParams.get("capture") !== "1";
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
  let csvObjectUrl;

  function readStep() {
    return /^#[1-9]$/.test(location.hash) ? Number(location.hash.slice(1)) : 1;
  }

  function buildUrl() {
    const url = new URL(location.href);
    if (active) url.searchParams.set("practice", active.key);
    else url.searchParams.delete("practice");
    if (mode === "reference") url.searchParams.set("mode", "reference");
    else url.searchParams.delete("mode");
    url.hash = String(step);
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

  function setCsvLink() {
    const link = byId("truth-download");
    if (csvObjectUrl) URL.revokeObjectURL(csvObjectUrl);
    csvObjectUrl = null;
    link.hidden = !active || active === reference;
    link.removeAttribute("href");
    if (link.hidden) return;
    if (offline) {
      csvObjectUrl = URL.createObjectURL(new Blob(["\uFEFF", offline.truth[active.key]], { type: "text/csv;charset=utf-8" }));
      link.href = csvObjectUrl;
    } else {
      link.href = "/api/truth/" + encodeURIComponent(active.key) + ".csv";
    }
  }

  function showStep(requested, syncView = true) {
    if (!active && requested !== 1) {
      openPractice(practices[0], requested);
      return;
    }
    const available = active?.availableSteps || allSteps;
    // A direct link to a missing tooltip opens its underlying table.
    step = available.includes(requested) ? requested : requested === 3 ? 2 : 5;
    const isList = step <= 3;
    list.hidden = !isList;
    detail.hidden = isList;
    byId("practice-tab").hidden = isList;
    byId("list-tab").setAttribute("aria-current", isList ? "page" : "false");
    byId("practice-tab").setAttribute("aria-current", isList ? "false" : "page");
    if (active && syncView) (isList ? window.BperList : window.BperDetail).show(step);
    screenSelect.value = String(step);
    for (const option of screenSelect.options) option.disabled = !available.includes(Number(option.value));
    byId("previous-screen").disabled = step === available[0];
    byId("next-screen").disabled = step === available.at(-1);
    original.hidden = mode !== "reference";
    frame.classList.toggle("reference", !original.hidden);
    if (!original.hidden) {
      const src = offline ? offline.screens[step] : "/reference/" + step + ".png";
      if (original.getAttribute("src") !== src) original.src = src;
    }
    syncUrl();
  }

  function openPractice(profile, requested = 4) {
    active = profile;
    if (!profile || profile !== reference) mode = "interactive";
    practiceSelect.value = profile?.key || "";
    modeSelect.value = mode;
    modeSelect.disabled = !reference || profile !== reference;
    const operator = profile || practices[0];
    byId("operator-name").textContent = operator.operatorName;
    byId("operator-codes").textContent = [operator.operatorId, operator.abi.padStart(5, "0"), operator.officeCode || operator.assignee].join("　");
    setCsvLink();
    if (profile) {
      byId("practice-caption").textContent = "PEF 2.0 - Pratica: " + profile.number;
      // Ignore delayed blur/scroll from a panel which navigation just closed.
      window.BperList.render(list, profile, {
        openPractice: () => showStep(4),
        onState: n => { if (active === profile && step <= 3) showStep(n, false); },
      });
      window.BperDetail.render(detail, profile, {
        onState: n => { if (active === profile && step >= 4) showStep(n, false); },
      });
    } else {
      detail.replaceChildren();
      window.BperList.directory(list, practices, { openPractice: p => openPractice(p) });
    }
    showStep(requested);
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
    const catalog = offline || await jsonAt("/api/practices.json");
    practices = catalog.practices;
    if (!practices?.length) throw new Error("Nessuna pratica nel database.");
    const profiles = new Map(practices.map(p => [p.key, p]));
    for (const p of practices) practiceSelect.add(new Option(p.name + " · " + p.number, p.key));
    if (catalog.hasReference) {
      reference = offline ? offline.practice : await jsonAt("/reference/practice.json");
      reference.key = "reference";
      reference.availableSteps = allSteps;
      profiles.set(reference.key, reference);
      practiceSelect.add(new Option("Pratica di riferimento", reference.key));
      modeSelect.hidden = false;
      document.querySelector('label[for="mode"]').hidden = false;
    }
    const fitFrame = () => frame.style.setProperty("--zoom", String(stage.clientWidth / frame.offsetWidth));
    fitFrame();
    new ResizeObserver(fitFrame).observe(stage);
    const key = initial.searchParams.get("practice") || (mode === "reference" ? "reference" : "");
    if (key && !profiles.has(key)) throw new Error("La pratica richiesta non è presente in questo catalogo.");
    const requested = readStep();
    openPractice(profiles.get(key) || (requested > 1 ? practices[0] : null), requested);
    frame.dataset.ready = "true";

    screenSelect.onchange = () => showStep(Number(screenSelect.value));
    byId("previous-screen").onclick = () => adjacent(-1);
    byId("next-screen").onclick = () => adjacent(1);
    byId("search-tab").onclick = () => openPractice(null, 1);
    byId("list-tab").onclick = () => showStep(1);
    byId("practice-tab").onclick = () => showStep(4);
    practiceSelect.onchange = () => openPractice(profiles.get(practiceSelect.value), practiceSelect.value ? step : 1);
    modeSelect.onchange = () => { mode = modeSelect.value; showStep(step); };
    byId("open-capture").onclick = () => {
      const url = buildUrl();
      url.searchParams.delete("console");
      url.searchParams.set("capture", "1");
      const popup = window.open(url.href, "nuova-pef-cattura",
        `popup,width=${frame.offsetWidth},height=${frame.offsetHeight},resizable=yes`);
      if (popup) popup.focus();
      else location.assign(url.href);
    };
    window.addEventListener("hashchange", () => showStep(readStep()));
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
        showStep(Number(event.key));
      }
    });
  }

  start().catch(error => {
    const message = byId("error-message");
    message.textContent = "Impossibile aprire il simulatore. " + error.message;
    message.hidden = false;
  });
})();
