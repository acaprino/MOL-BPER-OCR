/* Waits of Nuova PEF and of its PEF 2.0 frame, timed on the recordings (spec 7, 9, 18 item 6; 8 fps cuts of the main
   recording 01:31-02:04 and 17:56-18:21, MOL 01 01:10-01:16). With ?capture=1 or ?loading=off nothing waits: each
   action happens at once, so capture packs, the truth audit and the tests stay fast and pixel-identical. */
(() => {
  "use strict";

  const query = new URLSearchParams(location.search);
  const enabled = query.get("capture") !== "1" && query.get("loading") !== "off";

  // Milliseconds. Opening a practice, from the click on the menu item (main recording 01:55.4-02:02.8): the closed
  // menu left at the window's top left, the new tab over a blank area with the ring, the page half drawn and washed
  // out, then washed out alone, then at full contrast.
  const TIMES = {
    rowBusy: 500,       // kebab click -> row menu (18:10.6-18:11.1)
    ghost: 250,         // the closed menu at the top left (01:55.4, MOL 01 01:51.0)
    blank: 4625, partial: 1250, washed: 750, settle: 750,
    dialogBlank: 250,   // with the "già in lavorazione" dialog: blank and ring before it (18:12.1)
    dialogFade: 375,    // the grey comes up (18:12.4-18:12.75)
    confirmBlank: 375,  // after Conferma, blank without ring before the page (18:19.1-18:19.5)
    boot: 250, splash: 500, home: 375,  // app start: bare page, logo and ring, faded home (01:32.75-01:33.5)
    scheda: 4000,       // ASSUMPTION (spec 17.2): a BSpace procedure's tab stays on about:blank ~4 s
    // For run() below. A navigator move (Gestione Documentale -> Fidi, 8 fps cut 04:59.5-05:02.5) waited 3 s; an
    // inner tab, 1-2 s at 1 fps (spec 9, 10.3).
    navigator: 3000, innerTab: 1500,
  };

  // Runs [[ms, action], ...] in turn, each ms after the previous step; without waits all at once. Returns cancel().
  function sequence(steps) {
    let timer = null;
    let index = 0;
    const next = () => {
      while (index < steps.length) {
        const [ms, action] = steps[index++];
        if (enabled && ms > 0) {
          timer = setTimeout(() => { timer = null; action(); next(); }, ms);
          return;
        }
        action();
      }
    };
    next();
    return () => { clearTimeout(timer); index = steps.length; };
  }

  // ---- PEF 2.0 request (spec 9, frame 05m00s): red "Attendere... caricamento in corso" right under the mast line and
  // a navy ring in the middle of what the frame shows, for ms; then answer(). host is the PEF 2.0 root holding the
  // page (.pd-page) and the frame (.pd-window). A new request on the same host replaces the pending one.
  const pending = new Map();

  function stop(host) {
    clearTimeout(pending.get(host));
    pending.delete(host);
    host.querySelectorAll(":scope .ld-wait, :scope > .ld-spinner").forEach(node => node.remove());
  }

  function run(host, ms, answer) {
    stop(host);
    if (!enabled) {
      answer();
      return () => {};
    }
    host.querySelector(".pd-page").insertAdjacentHTML("beforeend",
      '<span class="ld-wait" role="status">Attendere... caricamento in corso</span>');
    // Centred on what the frame shows, like the original's fixed ring inside its iframe.
    const frame = host.querySelector(".pd-window");
    host.insertAdjacentHTML("beforeend", '<i class="ld-spinner" role="progressbar" aria-label="Caricamento in corso"></i>');
    const ring = host.lastElementChild;
    ring.style.left = frame.offsetLeft + frame.clientWidth / 2 + "px";
    ring.style.top = frame.offsetTop + frame.clientHeight / 2 + "px";
    pending.set(host, setTimeout(() => { stop(host); answer(); }, ms));
    return () => stop(host);
  }

  window.BperLoading = { enabled, TIMES, sequence, run, stop };
})();
