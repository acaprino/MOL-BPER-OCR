/* Home of Nuova PEF (video 01:35 and 17:59): the dashboard the application opens on. Its two selects,
   the five chips and the two placeholders stay disabled and unresolved for the 3 s the video shows the
   page, so nothing here loads; only RICERCA leads on, to the Ricerca Pratica tab. */
(() => {
  "use strict";

  const chips = ["CREDITO INTENZIONALE", "DELIBERA SEMPLIFICATA", "RESTITUITE", "IN ATTESA", "SOSPESE"];

  function render(root, { onSearch }) {
    root.innerHTML = `
      <div class="hm-content">
        <div class="hm-actions">
          <button type="button" class="hm-outline">RIEPILOGO RICHIESTA STAMPE</button>
          <button type="button" class="hm-primary">RICERCA</button>
        </div>
        <div class="hm-panel">
          <label class="hm-label" for="hm-origin">PROVENIENZA</label>
          <select id="hm-origin" class="hm-select" disabled><option>Tutte</option></select>
          <label class="hm-label hm-second" for="hm-odl">ODL</label>
          <select id="hm-odl" class="hm-select hm-second" disabled><option>Le mie pratiche</option></select>
          <div class="hm-chips" role="group" aria-label="Filtri rapidi">${chips
            .map(chip => `<button type="button" disabled>${chip}</button>`).join("")}</div>
          <div class="hm-skeletons" aria-busy="true"><div></div><div></div></div>
        </div>
      </div>`;
    // What "RIEPILOGO RICHIESTA STAMPE" opens was never shown: the button does nothing.
    root.querySelector(".hm-primary").addEventListener("click", () => onSearch());
  }

  window.BperHome = { render };
})();
