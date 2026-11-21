// Pack It Up: the sign-in page (start.html). A name and no password: it is kept in this browser
// (window.PIU.who) and sent with uploads, so a move can be found by name. Needs ui/api.js first.
(function () {
  "use strict";
  const { link, params, $ } = window.PIU;
  const next = () => link("capture.html", { run_id: params.get("run_id") });

  // Already signed in: go straight on, unless the person came here to change the name.
  if (window.PIU.who() && !params.get("change")) { location.replace(next()); return; }

  const input = $("#name");
  input.value = window.PIU.who();
  input.focus();
  $("#signin").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    window.PIU.setWho(name);
    // A browser that refuses to save (private mode) gets the name in the address instead, so the
    // capture page doesn't send the person straight back here.
    location.href = window.PIU.who() ? next() : link("capture.html", { run_id: params.get("run_id"), who: name });
  });
})();
