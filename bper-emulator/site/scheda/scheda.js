/* BPER Scheda Privati: one JSON object per customer fills every value on the page.
 *
 * Route: /schede/SchedaPrivati/#/schede/<ndg>/<schedaId>. Data: GET /api/scheda/<ndg>.json, or
 * window.BperOffline.schede[<ndg>] in the offline export. Schema (the values are display strings, except the
 * boolean employerRegistered and the list outgoings in details):
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
 *     employerNdg, employerFrom, employerTo, employerRegistered (NON CENSITO needs a named employer
 *     that is not registered), incomeChanneled, creditCardBalance, housing, housingFrom,
 *     outgoings: the USCITE CONTINUATIVE rows in page order, [{description, annualAmount, due, residual}]
 *     ([] for none)
 * Capture hooks: ?scroll=<px> scrolls the main column, ?noteScroll=<px> scrolls the note box. The body gets
 * data-ready="true" only when each one given is reached within 1 px; otherwise it gets
 * data-scroll-mismatch="<asked>/<got>" of the first one missed (the main column first) and never data-ready, so
 * a capture or an audit waiting for data-ready fails instead of labelling the wrong view.
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
    // One row per outgoing, in list order; the template's inputs have no data-bind, their values are set here.
    const template = document.getElementById("sp-outgoing").content.firstElementChild;
    document.querySelector(".sp-outgoings").replaceChildren(...data.details.outgoings.map((outgoing, n) => {
      const row = template.cloneNode(true);
      row.querySelector("h4").textContent = "USCITA CONTINUATIVA " + (n + 1);
      const values = [outgoing.description, outgoing.annualAmount, outgoing.due, outgoing.residual];
      row.querySelectorAll("input").forEach((input, k) => { input.value = values[k]; });
      return row;
    }));
    for (const node of document.querySelectorAll("[data-bind]")) {
      const value = String(valueAt(data, node.dataset.bind) ?? "");
      if ("value" in node) node.value = value;
      else node.textContent = value;
    }
    // data-show lists conditions separated by spaces, all of which must hold: "path" is truthy, "!path" is false.
    for (const node of document.querySelectorAll("[data-show]")) {
      node.hidden = !node.dataset.show.trim().split(/\s+/).every((condition) => {
        const negated = condition.startsWith("!");
        const value = valueAt(data, negated ? condition.slice(1) : condition);
        return negated ? value === false : Boolean(value);
      });
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
    const hooks = [["scroll", ".sp-main"], ["noteScroll", ".sp-notes textarea"]].filter(([name]) => query.has(name))
      .map(([name, selector]) => ({ asked: Number(query.get(name)), box: document.querySelector(selector) }));
    for (const { asked, box } of hooks) box.scrollTop = asked;
    // Written so that a value that is not a number never counts as reached.
    const missed = hooks.find(({ asked, box }) => !(Math.abs(box.scrollTop - asked) <= 1));
    if (missed) document.body.dataset.scrollMismatch = `${missed.asked}/${missed.box.scrollTop}`;
    else document.body.dataset.ready = "true";
  }

  start().catch(() => {
    document.querySelector(".sp-main").hidden = true;
    document.getElementById("sp-error").hidden = false;
  });
})();
