/* Ricerca Pratica of Nuova PEF (frame 01m39s and the 1 fps samples 01:38-01:42, 18:07-18:09): the form, its
   grey state while the search runs, and the match against the practices of the catalogue. The video shows the
   form closed and submitted with Enter; dropdown contents, the submit button below the fold and the
   "Unità Organizzativa" and "RICERCA ANAGRAFICA" panels were never seen. */
(() => {
  "use strict";

  // In the video the other criteria stay grey for two 1 fps samples before the list appears.
  const LATENCY = 1500;
  // The STATO list as frame 01m39s shows it, with the codes of the list's Stato column. LAV, ATT and SOSP were seen
  // as codes; ABB as a code only in the MOL lists, and RESP is a guess. "Ab..." is cut in the video: its full label
  // is assumed. The list goes on past "Ab...", unseen: every other state of the catalogue follows, in code order.
  const STATES = [["In Lavorazione", "LAV"], ["In Attesa", "ATT"], ["Sospesa", "SOSP"], ["Respinta", "RESP"],
                  ["Abbandonata", "ABB"]];
  // shortcut: labels of the states the form was never seen with (APP: the approved practices of the MOL 05/06
  // lists), invented; any other code shows as itself. Replace them if a recording shows the list open.
  const OTHER_LABELS = { APP: "Approvata" };

  function stateOptions(practices) {
    const known = new Set(STATES.map(([, code]) => code));
    const others = [...new Set(practices.map(p => p.state).filter(code => code && !known.has(code)))].sort();
    return [...STATES, ...others.map(code => [OTHER_LABELS[code] ?? code, code])];
  }

  function searchText(value) {
    return String(value ?? "").normalize("NFD").replace(/\p{M}/gu, "")
      .toLocaleLowerCase("it").replace(/['’\s-]+/g, " ").trim();
  }
  // Identifiers compare as typed, without leading zeros; an operator's matricola also without its "U".
  const identifier = value => String(value ?? "").trim().replace(/^0+(?=.)/, "");
  const matricola = value => identifier(String(value ?? "").trim().replace(/^u/i, ""));

  function match(practices, criteria) {
    return practices.filter(p =>
      String(p.abi ?? "").padStart(5, "0") === criteria.abi &&
      (!criteria.ndg || identifier(p.ndg) === identifier(criteria.ndg)) &&
      (!criteria.number || identifier(p.number) === identifier(criteria.number)) &&
      (!criteria.matricola || matricola(p.operatorId) === matricola(criteria.matricola)) &&
      (!criteria.nome || searchText(p.operatorName).includes(searchText(criteria.nome))) &&
      (!criteria.states.length || criteria.states.includes(p.state)) &&
      (!criteria.evidence || p.evidence === criteria.evidence) &&
      (!criteria.type || (p.typeCode ?? p.type) === criteria.type) &&
      (!criteria.phase || p.phase === criteria.phase));
  }

  function options(practices, read) {
    const seen = new Map();
    for (const p of practices) {
      const [value, label] = read(p);
      if (value && !seen.has(value)) seen.set(value, label);
    }
    return [...seen].sort(([a], [b]) => a.localeCompare(b));
  }

  const escape = value => String(value).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const optionTags = list => list.map(([value, label]) => `<option value="${escape(value)}">${escape(label)}</option>`).join("");

  function render(root, practices, { onSubmit }) {
    const evidences = options(practices, p => [p.evidence, p.evidence + (p.evidenceTooltip ? " - " + p.evidenceTooltip : "")]);
    const types = options(practices, p => [p.typeCode ?? p.type, p.typeName ?? p.type ?? p.typeCode]);
    const phases = options(practices, p => [p.phase, p.phase]);
    root.innerHTML = `
      <form class="rp-form" novalidate>
        <label class="rp-label" for="rp-abi" style="top:41.7px">ABI</label>
        <select id="rp-abi" class="rp-control rp-select" style="top:58.4px"><option value="05387">05387-BPER</option></select>
        <div class="rp-tabs" role="tablist">
          <button type="button" role="tab" aria-selected="true">NDG / Numero Pratica</button>
          <button type="button" role="tab" aria-selected="false" tabindex="-1">Unità Organizzativa</button>
        </div>
        <label class="rp-label" for="rp-ndg" style="top:170.2px">NDG RICHIEDENTE</label>
        <input id="rp-ndg" class="rp-control rp-ndg" autocomplete="off" style="top:187.6px">
        <button type="button" class="rp-registry" style="top:187.6px">RICERCA ANAGRAFICA</button>
        <label class="rp-label" for="rp-number" style="top:224.4px">N° PRATICA</label>
        <input id="rp-number" class="rp-control" autocomplete="off" style="top:241.8px">
        <hr class="rp-rule">
        <h3 class="rp-heading" style="top:313.1px">OPERATORE</h3>
        <label class="rp-label" for="rp-matricola" style="top:345.3px">MATRICOLA</label>
        <input id="rp-matricola" class="rp-control" autocomplete="off" style="top:362.7px">
        <label class="rp-label rp-col2" for="rp-nome" style="top:345.3px">NOME</label>
        <input id="rp-nome" class="rp-control rp-col2" autocomplete="off" style="top:362.7px">
        <h3 class="rp-heading" style="top:410.7px">DATI PRATICA</h3>
        <span class="rp-label" id="rp-state-label" style="top:442.2px">STATO</span>
        <button type="button" id="rp-state" class="rp-control rp-select rp-multi" aria-haspopup="true" aria-expanded="false"
          aria-labelledby="rp-state-label" style="top:458.9px"><span class="rp-value"></span></button>
        <div class="rp-options" role="group" aria-label="Stati" hidden>${stateOptions(practices)
          .map(([label, code]) => `<label><input type="checkbox" value="${escape(code)}" checked> ${escape(label)}</label>`).join("")}</div>
        <label class="rp-label rp-col2" for="rp-evidence" style="top:442.2px">EVIDENZE</label>
        <select id="rp-evidence" class="rp-control rp-select rp-col2" style="top:458.9px"><option value="">Seleziona</option>${optionTags(evidences)}</select>
        <label class="rp-label" for="rp-type" style="top:496.5px">TIPO PRATICA</label>
        <select id="rp-type" class="rp-control rp-select" style="top:513.2px"><option value="">Tutte</option>${optionTags(types)}</select>
        <label class="rp-label rp-col2" for="rp-origin" style="top:496.5px">PROVENIENZA</label>
        <select id="rp-origin" class="rp-control rp-select rp-col2" style="top:513.2px"><option value="">Tutte</option></select>
        <label class="rp-label rp-col3" for="rp-phase" style="top:496.5px">FASE</label>
        <select id="rp-phase" class="rp-control rp-select rp-col3" style="top:513.2px"><option value="">Tutte</option>${optionTags(phases)}</select>
        <button type="submit" class="rp-submit">RICERCA</button>
      </form>`;
    const form = root.querySelector("form");
    const get = id => root.querySelector("#rp-" + id);
    const state = get("state");
    const stateValue = state.firstElementChild;
    const panel = root.querySelector(".rp-options");
    const boxes = [...panel.querySelectorAll("input")];
    // The criteria greyed while the search runs (01:40-01:41 and 18:08): all but ABI and N° PRATICA.
    const greyed = ["ndg", "matricola", "nome", "state", "evidence", "type", "origin", "phase"].map(get);
    const submit = root.querySelector(".rp-submit");
    let busy = false;

    const chosen = () => boxes.filter(box => box.checked);
    const showStates = () => { stateValue.textContent = chosen().map(box => box.parentElement.textContent.trim()).join("; "); };
    function toggle(open) {
      panel.hidden = !open;
      state.setAttribute("aria-expanded", String(open));
    }
    showStates();
    state.addEventListener("click", () => toggle(panel.hidden));
    panel.addEventListener("change", showStates);
    root.addEventListener("keydown", event => {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        toggle(false);
        state.focus();
      }
    });
    root.addEventListener("pointerdown", event => {
      if (!panel.hidden && !panel.contains(event.target) && event.target !== state) toggle(false);
    });
    const placeholder = () => get("evidence").classList.toggle("rp-placeholder", !get("evidence").value);
    get("evidence").addEventListener("change", placeholder);
    placeholder();

    function selected(id) {
      const select = get(id);
      return [select.value, select.selectedOptions[0]?.text ?? ""];
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      if (busy) return;
      toggle(false);
      const text = id => get(id).value.trim();
      const states = chosen();
      // Every state chosen is no state criterion: a practice without a state (two of the archive) is found too.
      const criteria = {
        abi: get("abi").value, ndg: text("ndg"), number: text("number"), matricola: text("matricola"),
        nome: text("nome"), states: states.length < boxes.length ? states.map(box => box.value) : [],
        evidence: get("evidence").value,
        type: get("type").value, phase: get("phase").value,
      };
      // "Filtri Attivi" of the list: what the operator set, in the order of the form. Its real content was never
      // seen expanded; the one line the references carry is "NDG <ndg>".
      const filters = [["NDG", criteria.ndg], ["N° Pratica", criteria.number], ["Matricola", criteria.matricola],
        ["Nome", criteria.nome],
        ["Stato", states.length < boxes.length ? stateValue.textContent : ""],
        ["Evidenze", criteria.evidence && selected("evidence")[1]], ["Tipo Pratica", criteria.type && selected("type")[1]],
        ["Fase", criteria.phase && selected("phase")[1]]].filter(([, value]) => value);
      busy = true;
      for (const control of [...greyed, submit]) control.disabled = true;
      const answer = () => {
        busy = false;
        for (const control of [...greyed, submit]) control.disabled = false;
        onSubmit(match(practices, criteria), filters);
      };
      // ?capture=1 and ?loading=off answer at once (loading.js).
      if (window.BperLoading) window.BperLoading.sequence([[LATENCY, answer]]);
      else setTimeout(answer, LATENCY);
    });
  }

  window.BperSearch = { render, match };
})();
