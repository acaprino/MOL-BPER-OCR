/* BPER Scheda Privati: one JSON object per customer fills every value on the page.
 *
 * Route: /schede/SchedaPrivati/#/schede/<ndg>/<schedaId>. Data: GET /api/scheda/<ndg>.json, or
 * window.BperOffline.schede[<ndg>] in the offline export. Schema (all values are display strings):
 *   ndg, schedaId, name                     customer shown in the top bar
 *   operator: {code, name}                  user logged in, top of the sidebar
 *   lastChange: {when, user, branch, bank}  "Ultima modifica" block
 *   lastValidation: {user, branch, bank}    "Ultima validazione" block (its date is a field below)
 *   fields: the 13 extracted keys, exactly as displayed:
 *     professione_principale, dal, numero_mensilita, retribuzione_annua_netta, tipo_contratto,
 *     datore_di_lavoro_anagrafica, rating_ufficiale, score_cgs, nr_altri_componenti_nucleo,
 *     di_cui_percepiscono_reddito, importo_totale_annuo_nucleo,
 *     note_scheda_privati (paragraphs separated by blank lines), ultima_validazione_scheda
 *   details: shown but not extracted:
 *     employerNdg, employerFrom, employerTo, employerRegistered (false shows "NON CENSITO"),
 *     incomeChanneled, creditCardBalance, housing, housingFrom
 * Capture hooks: ?scroll=<px> scrolls the main column, ?noteScroll=<px> scrolls the note box.
 */
(() => {
  "use strict";

  function valueAt(data, path) {
    return path.split(".").reduce((node, key) => node?.[key], data);
  }

  async function load(ndg) {
    const offline = window.BperOffline;
    if (offline) return offline.schede?.[ndg];
    const response = await fetch("/api/scheda/" + encodeURIComponent(ndg) + ".json");
    return response.ok ? response.json() : undefined;
  }

  function render(data) {
    for (const node of document.querySelectorAll("[data-bind]")) {
      const value = String(valueAt(data, node.dataset.bind) ?? "");
      if ("value" in node) node.value = value;
      else node.textContent = value;
    }
    for (const node of document.querySelectorAll("[data-show]")) {
      const path = node.dataset.show;
      const shown = path.startsWith("!") ? valueAt(data, path.slice(1)) === false : Boolean(valueAt(data, path));
      node.hidden = !shown;
    }
  }

  // The hash is the route, so the menu scrolls without touching it.
  for (const button of document.querySelectorAll("[data-target]")) {
    button.addEventListener("click", () => document.getElementById(button.dataset.target)?.scrollIntoView());
  }

  async function start() {
    const route = /^#\/schede\/([^/]+)\/([^/]+)/.exec(location.hash);
    const data = route && await load(decodeURIComponent(route[1]));
    if (!data) throw new Error("missing scheda");
    render(data);
    const query = new URLSearchParams(location.search);
    if (query.has("noteScroll")) document.querySelector(".sp-notes textarea").scrollTop = Number(query.get("noteScroll"));
    if (query.has("scroll")) document.querySelector(".sp-main").scrollTop = Number(query.get("scroll"));
    document.body.dataset.ready = "true";
  }

  start().catch(() => {
    document.querySelector(".sp-main").hidden = true;
    document.getElementById("sp-error").hidden = false;
  });
})();
