/* GaugeBench Studio front end — vanilla JS, no build step. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, body) {
    let res;
    try {
      res = await fetch(path, body === undefined ? {} : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
    } catch (e) {
      console.warn("GaugeBench: request failed", path, e);
      const err = new Error("Can't reach GaugeBench Studio. Check that the app is still running, then try again.");
      err.data = { code: "offline" };
      throw err;
    }
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      if (data.detail) console.warn(`GaugeBench ${path} (${res.status} ${data.code}):`, data.detail);
      const err = new Error(data.error || "Something went wrong. Please try again.");
      err.data = data;
      throw err;
    }
    return data;
  }

  function taskExpired() {
    $$("#answer-form input, #answer-form button").forEach((el) => (el.disabled = true));
    $("#btn-ask").disabled = true;
    const n = $("#ticket-notice");
    n.hidden = false;
    n.innerHTML = `<span class="callout-icon" aria-hidden="true">⟳</span><div><b>This task has expired.</b>
      It was created before the app restarted, so it can't be scored any more.
      <button type="button" class="link-btn" id="notice-gen">Generate a new task</button></div>`;
    $("#notice-gen").addEventListener("click", () => generate());
  }
  const handleErr = (e) => (e.data?.code === "task_expired" ? taskExpired() : toast(e.message, true));

  let toastTimer;
  function toast(msg, err = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.toggle("err", err);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), err ? 6000 : 2600);
  }

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } },
  };

  // ------------------------------------------------------------------ vocab
  const FAMILY_ICONS = {
    read_value: `<circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" stroke-width="1.6"/><path class="ac" d="M16 16 L23 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M8 22 l2-1.2 M6.3 16 h2.3 M8 10 l2 1.2 M16 6.2 v2.3" stroke="currentColor" stroke-width="1.4"/>`,
    zone_status: `<path d="M7 22 A11 11 0 0 1 9.5 8.6" fill="none" stroke="#39e07f" stroke-width="3"/><path d="M9.5 8.6 A11 11 0 0 1 22.5 8.6" fill="none" stroke="#f5d33a" stroke-width="3"/><path d="M22.5 8.6 A11 11 0 0 1 25 22" fill="none" stroke="#ff4f4f" stroke-width="3"/><path class="ac" d="M16 18 L20 9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    setpoint_deviation: `<circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M16 16 L9 10" stroke="#ff4f4f" stroke-width="1.4" stroke-linecap="round"/><path class="ac" d="M16 16 L23 11" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>`,
    panel_alarm: `<rect x="4" y="4" width="11" height="11" rx="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="17" y="4" width="11" height="11" rx="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="4" y="17" width="11" height="11" rx="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect class="ac" x="17" y="17" width="11" height="11" rx="5.5" fill="rgba(255,79,79,.3)" stroke="#ff4f4f" stroke-width="1.6"/>`,
    panel_max: `<circle cx="9" cy="16" r="6" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="23" cy="16" r="6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M9 16 L12.5 12" stroke="currentColor" stroke-width="1.6"/><path class="ac" d="M23 16 L26 19" stroke="currentColor" stroke-width="1.8"/><path class="ac" d="M23 4 l-2 3 h4 z" fill="currentColor" stroke="currentColor" stroke-width="1"/>`,
    temporal_change: `<circle cx="10" cy="16" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="22" cy="16" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M10 16 L7 12" stroke="currentColor" stroke-width="1.6"/><path class="ac" d="M22 16 L26 13" stroke="currentColor" stroke-width="1.8"/><path d="M13 27 h6 l-2 -2 M19 27 l-2 2" fill="none" stroke="currentColor" stroke-width="1.2"/>`,
    dual_scale: `<circle cx="16" cy="16" r="11.5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="16" cy="16" r="6.5" fill="none" stroke="#ff4f4f" stroke-width="1.4" stroke-dasharray="2 2"/><path class="ac" d="M16 16 L24 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    level_reading: `<rect x="11" y="4" width="10" height="24" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/><rect class="ac" x="13" y="13" width="6" height="13" rx="1" fill="rgba(126,166,255,.55)" stroke="currentColor" stroke-width="1"/><path d="M23 8 h3 M23 13 h2 M23 18 h3 M23 23 h2" stroke="currentColor" stroke-width="1.2"/>`,
    dial_meter: `<circle cx="6.5" cy="16" r="4.6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="16" cy="16" r="4.6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="25.5" cy="16" r="4.6" fill="none" stroke="currentColor" stroke-width="1.3"/><path class="ac" d="M6.5 16 l2.4 -2.6 M16 16 l-2.6 -2.2 M25.5 16 l1.2 3.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M4 9.5 a4 4 0 0 1 5 0 M18.5 9.5 a4 4 0 0 0 -5 0" fill="none" stroke="#ff4f4f" stroke-width="1"/>`,
    vernier: `<rect x="3" y="8" width="26" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6 16 v-3 M9 16 v-2 M12 16 v-2 M15 16 v-3 M18 16 v-2 M21 16 v-2 M24 16 v-3" stroke="currentColor" stroke-width="1"/><rect class="ac" x="9" y="16" width="14" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/><path class="ac" d="M10 16 v3 M13 16 v2 M16 16 v3 M19 16 v2 M22 16 v3" stroke="currentColor" stroke-width="1"/>`,
    digital_display: `<rect x="3" y="8" width="26" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path class="ac" d="M7 12 h4 M11 12 v3.5 M7 15.5 h4 M7 15.5 v3.5 M7 19 h4 M14 12 h4 M18 12 v7 M21 12 h4 M21 12 v3.5 M21 15.5 h4 M25 15.5 v3.5 M21 19 h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
    panel_count: `<circle cx="9" cy="9" r="5" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="23" cy="9" r="5" fill="none" stroke="#ff4f4f" stroke-width="1.5"/><circle cx="9" cy="23" r="5" fill="none" stroke="#ff4f4f" stroke-width="1.5"/><circle cx="23" cy="23" r="5" fill="none" stroke="currentColor" stroke-width="1.3"/><text class="ac" x="16" y="19" font-size="8" text-anchor="middle" fill="currentColor" font-family="monospace" font-weight="700">2</text>`,
  };

  const FACTOR_LABEL = {
    scale_kind: "Scale", sweep: "Sweep", minors_per_major: "Minors", label_every: "Labels", multiplier: "Multiplier",
    face: "Face", glare: "Glare", tilt: "Tilt", blur: "Blur", noise: "Noise", lighting: "Light",
  };
  const DIAL_FACTORS = ["scale_kind", "sweep", "minors_per_major", "label_every", "multiplier", "face"];
  const PHOTO_FACTORS = ["glare", "tilt", "blur", "noise", "lighting"];

  function fmtFactor(name, v) {
    switch (name) {
      case "scale_kind": return { linear: "linear", offset: "offset", sqrt: "√ sqrt", log: "log" }[v] || v;
      case "sweep": return `${v}°`;
      case "minors_per_major": return `${v}`;
      case "label_every": return Number(v) === 1 ? "all" : "alt.";
      case "multiplier": return String(v).replace("x", "×");
      case "glare": return ["off", "soft", "hard"][Number(v)] ?? v;
      case "tilt": return `${v}°`;
      case "blur": return Number(v) === 0 ? "sharp" : `σ${Number(v).toFixed(1)}`;
      case "noise": return Number(v) === 0 ? "clean" : `σ${Number(v)}`;
      case "lighting": return `${Math.round(Number(v) * 100)}%`;
      default: return String(v);
    }
  }

  const CHECK_NAMES = {
    pixel_reread_needle: "Pixel re-read matches the key",
    pixel_reread_setpoint: "Set-point re-read matches",
    pixel_reread_needle_secondary: "Inner-ring re-read matches",
    needle_present: "Needle is visible", setpoint_present: "Set-point needle is visible",
    needle_not_glared: "Needle not hidden by glare", setpoint_not_glared: "Set point not hidden by glare",
    needle_contrast: "Needle stands out from the face", setpoint_contrast: "Set point stands out",
    tick_divisions_resolvable: "Tick marks far enough apart", labels_legible: "Printed numbers big enough",
    labels_do_not_overlap: "Printed numbers don't overlap",
    needle_clear_of_zone_boundary: "Needle clear of a zone boundary",
    all_needles_clear_of_zone_boundaries: "All needles clear of zone boundaries",
    all_needles_clear_of_danger_boundary: "All needles clear of the red-zone edge",
    winner_clear_margin: "Highest gauge wins by a clear margin", needles_separated: "Needles far enough apart",
    change_larger_than_reading_error: "Change is bigger than reading error",
    pixel_reread_dials: "Every dial re-read from pixels", pointers_clear_of_numbers: "No pointer sits exactly on a number",
    pixel_reread_vernier: "Vernier re-read from tick pixels", vernier_alignment_resolvable: "Aligned line clearly resolvable",
    pixel_reread_digits: "Segments decoded from pixels",
  };
  const checkName = (n) => CHECK_NAMES[n] || (n.startsWith("reject:") ? "Sampler: " + n.slice(7).replace(/_/g, " ")
    : n.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()));
  const REJECT_SHORT = {
    needle_not_glared: "Glare over the needle", setpoint_not_glared: "Glare over the set point",
    labels_do_not_overlap: "Numbers overlap", needle_contrast: "Needle too faint", setpoint_contrast: "Set point too faint",
    tick_divisions_resolvable: "Ticks too dense", labels_legible: "Numbers too small",
    needle_clear_of_zone_boundary: "Needle on a zone edge", all_needles_clear_of_zone_boundaries: "Needle on a zone edge",
    all_needles_clear_of_danger_boundary: "Needle on the red edge", winner_clear_margin: "No clear winner",
    needles_separated: "Needles overlap", change_larger_than_reading_error: "Change too small to read",
    pixel_reread_needle: "Pixel re-read disagrees", pixel_reread_setpoint: "Set-point re-read disagrees",
    pointers_clear_of_numbers: "Pointer on a number", vernier_alignment_resolvable: "Alignment too subtle",
    pixel_reread_dials: "Dial re-read disagrees", pixel_reread_vernier: "Vernier re-read disagrees",
    pixel_reread_digits: "Segments unreadable",
  };
  const rejectShort = (n) => REJECT_SHORT[n] || checkName(n);

  function fmtNum(v, prec = 6) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const s = Math.abs(n) >= 1e9 || (Math.abs(n) < 1e-4 && n !== 0) ? n.toExponential(2) : String(+n.toPrecision(prec));
    return s.replace("-", "−");
  }
  const fmtExact = (v) => fmtNum(v, 12);           // what someone typed: never round it away
  function fmtTol(tu) {
    if (tu == null || !Number.isFinite(Number(tu))) return "";
    const x = Number(tu);
    return x < 10 ? `${x.toFixed(1)}×` : x < 1000 ? `${Math.round(x)}×` : ">1000×";
  }
  const MARKER = { vernier: "Vernier lines", digital_display: "Lit segments", dial_meter: "Pointers", level_reading: "Liquid surface" };
  function checkNameFor(n, family) {
    const m = MARKER[family];
    if (m && n === "needle_not_glared") return `${m} not hidden by glare`;
    if (m && n === "needle_contrast") return `${m} stand out from the background`;
    return checkName(n);
  }
  const isNarrow = () => window.innerWidth < 860;
  const scrollOnPhone = (el) => { if (isNarrow() && el) el.scrollIntoView({ behavior: "smooth", block: "start" }); };

  // ------------------------------------------------------------------ state
  const S = {
    meta: null,
    family: store.get("gb-family", "read_value"),
    factors: {},
    task: null,
    answered: false,
    choice: null,
    tally: store.get("gb-tally", { you: [0, 0], gem: [0, 0] }),
    seedLocked: false,
    lastKey: null,
    lastYou: null,
    lastGem: null,
    archive: { suite: null, model: null, outcome: "all", family: null, search: "", data: null },
  };

  // ------------------------------------------------------------------ knobs
  document.body.insertAdjacentHTML("beforeend", `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <radialGradient id="knob-grad" cx="38%" cy="30%" r="75%"><stop offset="0" stop-color="#4a5058"/><stop offset=".55" stop-color="#2a2e34"/><stop offset="1" stop-color="#16181b"/></radialGradient>
  </defs></svg>`);

  class Knob {
    constructor(name, values, value, onChange) {
      this.name = name; this.values = values; this.onChange = onChange;
      this.i = Math.max(0, values.findIndex((v) => String(v) === String(value)));
      this.el = h("div", {
        class: "knob", role: "slider", tabindex: "0", "aria-label": FACTOR_LABEL[name],
        "aria-valuemin": "0", "aria-valuemax": String(values.length - 1),
      });
      const n = values.length;
      const ang = (i) => (n === 1 ? 0 : -135 + (270 * i) / (n - 1));
      const ticks = values.map((_, i) => {
        const a = (ang(i) - 90) * Math.PI / 180;
        return `<circle class="k-tick" data-i="${i}" cx="${29 + 26 * Math.cos(a)}" cy="${29 + 26 * Math.sin(a)}" r="2.2"/>`;
      }).join("");
      this.angles = values.map((_, i) => ang(i));
      this.el.innerHTML = `<svg viewBox="0 0 58 58">${ticks}
        <circle class="k-body" cx="29" cy="29" r="19"/><circle class="k-rim" cx="29" cy="29" r="16"/>
        <g class="k-pointer"><line x1="29" y1="29" x2="29" y2="13.5"/></g></svg>
        <span class="k-value"></span><span class="k-label">${FACTOR_LABEL[name]}</span>`;
      this.pointer = $(".k-pointer", this.el);
      this.valueEl = $(".k-value", this.el);
      this.bind();
      this.render(false);
    }
    get value() { return this.values[this.i]; }
    set(i, fire = true) {
      const n = this.values.length;
      const j = ((i % n) + n) % n;
      if (j === this.i) return;
      this.i = j; this.render(fire);
    }
    setValue(v) {
      const i = this.values.findIndex((x) => String(x) === String(v));
      if (i >= 0) { this.i = i; this.render(false); }
    }
    render(fire) {
      this.pointer.style.transform = `rotate(${this.angles[this.i]}deg)`;
      $$(".k-tick", this.el).forEach((t) => t.classList.toggle("is-on", Number(t.dataset.i) <= this.i));
      const txt = fmtFactor(this.name, this.value);
      this.valueEl.textContent = txt;
      this.el.setAttribute("aria-valuenow", String(this.i));
      this.el.setAttribute("aria-valuetext", txt);
      const base = S.meta?.base?.[this.name];
      this.el.classList.toggle("is-changed", base != null && String(base) !== String(this.value));
      if (fire) { this.onChange(this.name, this.value); sfx.tick(); }
    }
    bind() {
      let startY = 0, startI = 0, dragging = false, moved = false;
      this.el.addEventListener("pointerdown", (e) => {
        dragging = true; moved = false; startY = e.clientY; startI = this.i;
        this.el.setPointerCapture(e.pointerId);
      });
      this.el.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        const steps = Math.round((startY - e.clientY) / 16);
        if (steps !== 0) moved = true;
        const j = Math.max(0, Math.min(this.values.length - 1, startI + steps));
        if (j !== this.i) { this.i = j; this.render(true); }
      });
      this.el.addEventListener("pointerup", (e) => {
        if (dragging && !moved) this.set(this.i + (e.shiftKey ? -1 : 1));
        dragging = false;
      });
      this.el.addEventListener("wheel", (e) => {
        e.preventDefault();
        const j = Math.max(0, Math.min(this.values.length - 1, this.i + (e.deltaY < 0 ? 1 : -1)));
        if (j !== this.i) { this.i = j; this.render(true); }
      }, { passive: false });
      this.el.addEventListener("keydown", (e) => {
        const k = e.key;
        let j = this.i;
        if (k === "ArrowUp" || k === "ArrowRight") j++;
        else if (k === "ArrowDown" || k === "ArrowLeft") j--;
        else if (k === "Home") j = 0;
        else if (k === "End") j = this.values.length - 1;
        else return;
        e.preventDefault(); e.stopPropagation();
        j = Math.max(0, Math.min(this.values.length - 1, j));
        if (j !== this.i) { this.i = j; this.render(true); }
      });
    }
  }
  const knobs = {};

  // ------------------------------------------------------------------ bench setup
  function buildRack() {
    const fams = $("#families");
    fams.innerHTML = "";
    for (const f of S.meta.families) {
      const b = h("button", {
        class: "fam", role: "radio", "aria-checked": String(f.id === S.family), "data-family": f.id,
        html: `<svg viewBox="0 0 32 32" aria-hidden="true">${FAMILY_ICONS[f.id] || ""}</svg><span>${esc(f.label)}</span>`,
      });
      b.addEventListener("click", () => selectFamily(f.id));
      fams.append(b);
    }
    if (!S.meta.families.some((f) => f.id === S.family)) S.family = "read_value";
    const saved = store.get("gb-factors", {});
    for (const [name, dom] of Object.entries(S.meta.factors)) {
      S.factors[name] = dom.some((v) => String(v) === String(saved[name])) ? saved[name] : S.meta.base[name];
    }
    for (const [group, names] of [["#knobs-dial", DIAL_FACTORS], ["#knobs-photo", PHOTO_FACTORS]]) {
      const box = $(group);
      box.innerHTML = "";
      for (const name of names) {
        const k = new Knob(name, S.meta.factors[name], S.factors[name], (n, v) => {
          S.factors[n] = v; store.set("gb-factors", S.factors);
        });
        knobs[name] = k;
        box.append(k.el);
      }
    }
  }

  function selectFamily(id) {
    S.family = id;
    store.set("gb-family", id);
    $$(".fam").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.family === id)));
    const used = S.meta.applicable?.[id] || Object.keys(S.meta.factors);
    const label = S.meta.families.find((f) => f.id === id)?.label || id;
    for (const [name, k] of Object.entries(knobs)) {
      const on = used.includes(name);
      k.el.classList.toggle("is-na", !on);
      k.el.title = on ? "" : `Not used by ${label}: this instrument fixes it`;
    }
  }

  function setFactors(f) {
    for (const [name, v] of Object.entries(f)) {
      if (!knobs[name]) continue;
      knobs[name].setValue(v);
      if (S.meta.factors[name].some((x) => String(x) === String(v))) S.factors[name] = v;
    }
    store.set("gb-factors", S.factors);
  }

  // ------------------------------------------------------------------ generate
  let stageTimer;
  async function generate(level) {
    const btn = $("#btn-generate");
    if (btn.disabled) return;
    btn.disabled = true;
    btn.classList.add("is-pressed");
    setTimeout(() => btn.classList.remove("is-pressed"), 140);
    const vp = $("#viewport");
    vp.classList.add("is-busy");
    $(".brand").classList.add("is-busy");
    const stages = ["Synthesising", "Rendering dial", "Photographing", "Validating pixels"];
    let si = 0;
    $("#scan-stage").textContent = stages[0];
    stageTimer = setInterval(() => { si = (si + 1) % stages.length; $("#scan-stage").textContent = stages[si]; }, 650);

    const seedVal = $("#seed").value.trim();
    try {
      const lvl = Number.isInteger(level) ? level : undefined;
      const t = await api("/api/generate", { family: S.family, factors: S.factors, level: lvl, seed: /^\d+$/.test(seedVal) ? seedVal : undefined });
      if (lvl) setFactors(t.factors);
      showTask(t);
    } catch (e) {
      toast(e.message, true);
      if (e.data && e.data.rejected) {
        renderFloor({ rejected: e.data.rejected });
        $("#floor-sub").textContent = `All ${e.data.rejected.length} candidates were rejected, so nothing was published. The factory never asks an unreadable question.`;
      }
    } finally {
      clearInterval(stageTimer);
      vp.classList.remove("is-busy");
      $(".brand").classList.remove("is-busy");
      btn.disabled = false;
    }
  }

  function showTask(t) {
    S.task = t; S.answered = false; S.choice = null; S.lastKey = null; S.lastYou = null; S.lastGem = null; S.checksFull = null;
    const vp = $("#viewport");
    const img = $("#task-img");
    img.src = $("#tg-vision").checked ? t.vision : t.image;
    img.alt = `${t.family_label} task image`;
    vp.classList.remove("has-img"); void vp.offsetWidth; vp.classList.add("has-img");
    $("#task-id").textContent = t.id;
    $("#btn-link").disabled = false;
    if (S.seedLocked) $("#seed").value = t.seed;
    else { $("#seed").value = ""; $("#seed").placeholder = `random · last ${t.seed}`; }

    const passed = t.checks.filter((c) => c.passed).length;
    $("#inspect-foot").innerHTML = `
      <span>accepted on attempt <b>${t.attempts}</b>/25</span>
      <span><b>${t.ms}</b> ms</span>
      <span class="ok">${passed}/${t.checks.length} checks passed</span>
      <span>seed <b>${t.seed}</b></span>`;

    renderFloor(t);
    renderChecks(t.checks);
    renderTicket(t);
    scrollOnPhone($(".inspect"));
    const needle = $(".bd-needle");
    needle.style.transform = `rotate(${-110 + Math.random() * 220}deg)`;
  }

  function renderFloor(t) {
    const strip = $("#floor-strip");
    strip.innerHTML = "";
    const n = t.rejected.length;
    $("#floor-sub").textContent = n
      ? `${n} candidate${n > 1 ? "s" : ""} rejected before this task was accepted. Nobody, human or model, is ever asked an unreadable question.`
      : "Accepted on the first attempt.";
    if (!n) { strip.append(h("div", { class: "floor-ok" }, "Nothing rejected: the first candidate passed every check.")); return; }
    t.rejected.forEach((r, i) => {
      const why = r.reasons.map((x) => rejectShort(x.name));
      const uniq = [...new Set(why)];
      const card = h("div", { class: "reject" + (r.thumb ? "" : " no-img"), style: `animation-delay:${i * 70}ms`, title: r.reasons.map((x) => `${x.name}: ${x.detail}`).join("\n") },
        r.thumb ? h("img", { src: r.thumb, alt: "rejected candidate" }) : null,
        r.thumb ? h("span", { class: "rj-stamp" }, "REJECT") : null,
        h("div", { class: "rj-body" },
          h("div", { class: "rj-n" }, `attempt ${r.attempt}`),
          h("div", { class: "rj-why" }, uniq.slice(0, 2).join(" · ") + (uniq.length > 2 ? ` +${uniq.length - 2}` : ""))));
      strip.append(card);
    });
  }

  function renderChecks(checks) {
    const ul = $("#check-list");
    ul.innerHTML = "";
    checks.forEach((c, i) => {
      ul.append(h("li", { style: `animation-delay:${i * 35}ms` },
        h("span", { class: `led ${c.passed ? "pass" : "fail"}` }),
        h("span", { class: "check-name" }, checkNameFor(c.name, S.task?.family)),
        h("span", { class: "check-detail" }, c.detail)));
    });
    const p = checks.filter((c) => c.passed).length;
    $("#checks-count").textContent = `${p}/${checks.length} PASS`;
  }

  function renderTicket(t) {
    $("#ticket-no").textContent = "#" + Number(t.seed).toString(16).toUpperCase().padStart(10, "0");
    $("#ticket-family").textContent = t.family_label;
    $("#ticket-q").textContent = t.question;
    const form = $("#answer-form");
    form.hidden = false;
    $$("input, button", form).forEach((el) => (el.disabled = false));
    $("#verdict").hidden = true;
    $("#ticket-notice").hidden = true;
    $("#ticket-hint").hidden = true;
    S.hinted = false;
    $("#gemini-box").hidden = true;
    $("#gem-result").hidden = true;
    $("#gem-wait").hidden = true;
    $("#btn-ask").hidden = false;
    $("#btn-ask").disabled = false;
    const num = t.answer_type === "number";
    $("#answer-num").hidden = !num;
    const ch = $("#answer-choices");
    ch.hidden = num;
    ch.innerHTML = "";
    if (num) {
      $("#answer-input").value = "";
      $("#answer-unit").textContent = t.unit || "";
      setTimeout(() => $("#answer-input").focus({ preventScroll: true }), 50);
    } else {
      t.choices.forEach((c, i) => {
        const b = h("button", { type: "button", class: "choice", role: "radio", "aria-checked": "false", title: `key ${i + 1}` }, c);
        b.addEventListener("click", () => {
          S.choice = c;
          $$(".choice", ch).forEach((x) => x.setAttribute("aria-checked", String(x === b)));
        });
        ch.append(b);
      });
    }
    $("#ticket-spec").innerHTML = Object.entries(t.factors)
      .map(([k, v]) => `<span class="spec-chip">${esc(FACTOR_LABEL[k] || k)} <b>${esc(fmtFactor(k, v))}</b></span>`).join("");
  }

  // ------------------------------------------------------------------ answer + verdict
  async function submitAnswer(e) {
    e?.preventDefault();
    const t = S.task;
    if (!t || S.answered) return;
    const raw = t.answer_type === "number" ? $("#answer-input").value.trim().replace(",", ".") : S.choice;
    if (raw == null || raw === "") { toast(t.answer_type === "number" ? "Type your reading first." : "Pick an option first."); return; }
    try {
      const r = await api("/api/answer", { id: t.id, answer: raw });
      S.answered = true;
      S.lastKey = r.key;
      S.lastYou = r.score.parsed;
      bump("you", r.score.correct);
      record({ f: t.family, c: r.score.correct, tu: r.score.err_tol_units ?? null, h: !!S.hinted, m: "bench" });
      showVerdict(r.score.correct ? "pass" : "fail", r.key, r.score);
      if (r.checks) { S.checksFull = r.checks; renderChecks(r.checks); }
    } catch (err) { handleErr(err); }
  }

  async function reveal() {
    const t = S.task;
    if (!t || S.answered) return;
    try {
      const r = await api("/api/reveal", { id: t.id });
      S.answered = true;
      S.lastKey = r.key;
      showVerdict("reveal", r.key, null);
      if (r.checks) { S.checksFull = r.checks; renderChecks(r.checks); }
    } catch (err) { handleErr(err); }
  }

  function showVerdict(kind, key, sc) {
    $$("#answer-form input, #answer-form button").forEach((el) => (el.disabled = true));
    const v = $("#verdict");
    v.hidden = false;
    const stamp = $("#stamp");
    stamp.className = "stamp " + kind;
    stamp.textContent = kind === "pass" ? "PASS" : kind === "fail" ? "FAIL" : "KEY";
    void stamp.offsetWidth;
    sfx.stamp();
    if (kind === "pass") sfx.pass(); else if (kind === "fail") sfx.fail();
    renderReadout();
    $("#gemini-box").hidden = false;
    const avail = S.meta.gemini.available;
    $("#btn-ask").disabled = !avail;
    $("#btn-ask").title = avail ? `Send this exact image and question to ${S.meta.gemini.model}`
      : S.meta.public ? "Ask Gemini is turned off on this server" : "Add GEMINI_API_KEY to .env and restart the app";
    scrollOnPhone(v);
  }

  function renderReadout() {
    const key = S.lastKey, t = S.task;
    const num = key.answer_type === "number";
    const unit = key.unit ? ` ${key.unit}` : "";
    const rows = [];
    if (S.lastYou !== null && S.lastYou !== undefined) {
      rows.push(["You", num ? fmtExact(S.lastYou) + unit : S.lastYou, "r-you"]);
    }
    rows.push(["Key", num ? `${fmtNum(key.answer)} ± ${fmtNum(key.tolerance)}${unit}` : key.answer, ""]);
    if (S.hinted && S.lastYou != null) rows.push(["Assist", "hint used", ""]);
    if (S.lastGem) rows.push(["Gemini", S.lastGem.parsed == null ? "no answer" : (num ? fmtExact(S.lastGem.parsed) + unit : S.lastGem.parsed), "r-gem"]);
    if (num && S.lastYou != null && key.tolerance) {
      const tu = Math.abs(S.lastYou - key.answer) / key.tolerance;
      rows.push(["Your error", `${fmtTol(tu)} tolerance`, ""]);
    }
    $("#readout").innerHTML = rows.map(([a, b, c]) => `<dt>${a}</dt><dd class="${c}">${esc(b)}</dd>`).join("");
    const strip = $("#strip");
    if (num) { strip.style.display = "block"; drawStrip(strip, key, S.lastYou, S.lastGem?.parsed); }
    else strip.style.display = "none";
    void t;
  }

  function niceStep(span) {
    const raw = span / 4;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const m = raw / p;
    return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
  }

  function drawStrip(svg, key, you, gem) {
    const W = svg.clientWidth || 320, H = 78, pad = 14, y = 40;
    const k = Number(key.answer), tol = Number(key.tolerance) || Math.abs(k) * 0.02 || 1;
    let span = tol * 3.2;
    for (const v of [you, gem]) if (v != null && Number.isFinite(Number(v))) span = Math.max(span, Math.abs(v - k) * 1.25 + tol);
    const lo = k - span, hi = k + span;
    const x = (v) => pad + ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (W - 2 * pad);
    const step = niceStep(hi - lo);
    let ticks = "";
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
      ticks += `<line class="s-tick" x1="${x(v)}" x2="${x(v)}" y1="${y - 4}" y2="${y + 4}"/>
                <text class="s-tlabel" x="${x(v)}" y="${y + 17}" text-anchor="middle">${fmtNum(+v.toPrecision(6))}</text>`;
    }
    const mark = (v, color, label, up) => {
      if (v == null || !Number.isFinite(Number(v))) return "";
      const X = x(Number(v));
      const tri = up ? `M${X} ${y - 3} l-6 -10 h12 z` : `M${X} ${y + 3} l-6 10 h12 z`;
      const ty = up ? y - 18 : y + 31;
      return `<g class="s-mark"><path d="${tri}" fill="${color}"/>
        <text class="s-mark-label" x="${X}" y="${ty}" text-anchor="middle" fill="${color}">${label}</text></g>`;
    };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = `
      <rect class="s-band" x="${x(k - tol)}" y="${y - 9}" width="${Math.max(2, x(k + tol) - x(k - tol))}" height="18" rx="3"/>
      <line class="s-axis" x1="${pad}" x2="${W - pad}" y1="${y}" y2="${y}"/>
      ${ticks}
      <line class="s-key" x1="${x(k)}" x2="${x(k)}" y1="${y - 12}" y2="${y + 12}"/>
      ${mark(you, "#c94a08", "YOU", true)}
      ${mark(gem, "#3d63c9", "GEMINI", false)}`;
    svg.setAttribute("aria-label", `Key ${fmtNum(k)} plus or minus ${fmtNum(tol)}` + (you != null ? `, you ${fmtNum(you)}` : "") + (gem != null ? `, Gemini ${fmtNum(gem)}` : ""));
  }

  // ------------------------------------------------------------------ Gemini
  async function askGemini() {
    const t = S.task;
    if (!t) return;
    const btn = $("#btn-ask");
    btn.hidden = true;
    const wait = $("#gem-wait");
    wait.hidden = false;
    const t0 = Date.now();
    const timer = setInterval(() => { $("#gem-wait-text").textContent = `${S.meta.gemini.model} is reading the gauge… ${Math.round((Date.now() - t0) / 1000)}s`; }, 500);
    const out = $("#gem-result");
    try {
      const r = await api("/api/ask", { id: t.id });
      S.lastGem = r.score;
      if (!S.lastKey) S.lastKey = r.key;
      bump("gem", r.score.correct);
      out.hidden = false;
      const val = r.score.parsed == null ? "no parsable answer" : r.score.parsed;
      out.innerHTML = `<div class="gem-line"><span class="gem-chip ${r.score.correct ? "pass" : "fail"}">${r.score.correct ? "✓ CORRECT" : "✗ WRONG"}</span>
        <span>Gemini answered <b>${esc(typeof val === "number" ? fmtExact(val) : val)}</b> in ${r.seconds}s</span></div>
        <details><summary>Gemini's reasoning</summary><pre>${esc(r.text)}</pre></details>`;
      renderReadout();
    } catch (e) {
      btn.hidden = false;
      if (e.data?.code === "task_expired") { out.hidden = true; taskExpired(); return; }
      out.hidden = false;
      const quota = ["gemini_quota", "gemini_missing", "gemini_rate_limited"].includes(e.data?.code);
      if (quota) btn.disabled = true;               // retrying won't help until tomorrow / until set up
      out.innerHTML = `<div class="callout callout-err" role="alert"><span class="callout-icon" aria-hidden="true">!</span>
        <div>${esc(e.message)}</div></div>`;
    } finally {
      clearInterval(timer);
      wait.hidden = true;
    }
  }

  function bump(who, ok) {
    S.tally[who][1] += 1;
    if (ok) S.tally[who][0] += 1;
    store.set("gb-tally", S.tally);
    renderTally(who);
  }
  function renderTally(flash) {
    const f = (a) => `${String(a[0]).padStart(2, "0")}/${String(a[1]).padStart(2, "0")}`;
    $("#tally-you").textContent = f(S.tally.you);
    $("#tally-gem").textContent = f(S.tally.gem);
    const hist = getHistory();
    const rk = rankOf(hist);
    const chip = $("#rank-chip");
    chip.textContent = rk.name;
    chip.title = rk.acc == null ? `Answer ${rk.need} more to get ranked` : `Recent accuracy ${rk.acc.toFixed(0)}%`;
    const st = currentStreak(hist), sEl = $("#streak");
    const was = sEl.textContent;
    sEl.hidden = st < 2;
    sEl.textContent = st >= 2 ? `🔥${st}` : "";
    if (st >= 2 && was !== sEl.textContent) { sEl.classList.remove("pop"); void sEl.offsetWidth; sEl.classList.add("pop"); }
    if (flash) {
      const led = $(`[data-led="${flash}"]`);
      led.classList.add("on");
      setTimeout(() => led.classList.remove("on"), 1400);
    }
  }

  // ------------------------------------------------------------------ loupe
  function attachLoupe(vp, img, lens, enabled) {
    const Z = 2.6;
    const move = (e) => {
      if (!enabled() || !img.naturalWidth) return;
      const r = vp.getBoundingClientRect();
      const ir = img.getBoundingClientRect();
      const px = e.clientX - ir.left, py = e.clientY - ir.top;
      const sz = lens.offsetWidth || 170;
      lens.style.left = `${e.clientX - r.left - sz / 2}px`;
      lens.style.top = `${e.clientY - r.top - sz / 2}px`;
      lens.style.backgroundImage = `url("${img.src}")`;
      lens.style.backgroundSize = `${ir.width * Z}px ${ir.height * Z}px`;
      lens.style.backgroundPosition = `${-(px * Z - sz / 2)}px ${-(py * Z - sz / 2)}px`;
    };
    vp.addEventListener("pointermove", move);
    vp.addEventListener("pointerenter", (e) => { vp.classList.add("is-hover"); move(e); });
    vp.addEventListener("pointerleave", () => vp.classList.remove("is-hover"));
  }

  // ------------------------------------------------------------------ archive
  const BASELINES = ["oracle", "near_miss", "random", "shortcut"];
  const modelLabel = (m) => (BASELINES.includes(m) ? `${m} (baseline)` : m);

  function initArchive() {
    const suites = S.meta.suites;
    const seg = $("#suite-seg");
    seg.innerHTML = "";
    if (!suites.length) {
      $("#archive-empty").hidden = false;
      $("#archive-empty").innerHTML = `No generated suites found in <code>runs/</code>.<br>Create one with <code>python -m gaugebench all runs/demo --per-family 4 --sweep 1</code>.`;
      return;
    }
    const withModel = suites.filter((s) => s.models.some((m) => !BASELINES.includes(m)));
    const pick = (withModel.length ? withModel : suites).reduce((a, b) => (b.tasks > a.tasks ? b : a));
    for (const s of suites) {
      const b = h("button", { "data-suite": s.name }, s.name, h("span", { class: "seg-n" }, String(s.tasks)));
      b.addEventListener("click", () => loadSuite(s.name));
      seg.append(b);
    }
    loadSuite(store.get("gb-suite", pick.name) in Object.fromEntries(suites.map((s) => [s.name, 1])) ? store.get("gb-suite", pick.name) : pick.name);
  }

  async function loadSuite(name) {
    S.archive.suite = name;
    store.set("gb-suite", name);
    $$("#suite-seg button").forEach((b) => b.classList.toggle("is-on", b.dataset.suite === name));
    // placeholder cards while a big suite loads (a cold hosted server can take a few seconds)
    $("#cards").innerHTML = Array.from({ length: 12 }, () => `<div class="card card-skel" aria-hidden="true"><div></div><p></p><p></p></div>`).join("");
    $("#cards").setAttribute("aria-busy", "true");
    try {
      const d = await api(`/api/suite?name=${encodeURIComponent(name)}`);
      if (S.archive.suite !== name) return;          // the user already picked another suite
      $("#cards").removeAttribute("aria-busy");
      S.archive.data = d;
      const models = Object.keys(d.results);
      const sel = $("#model-select");
      sel.innerHTML = models.length ? "" : `<option value="">(no results yet)</option>`;
      const real = models.filter((m) => !BASELINES.includes(m));
      for (const m of [...real, ...models.filter((m) => BASELINES.includes(m))]) sel.append(h("option", { value: m }, modelLabel(m)));
      S.archive.model = real[0] || models[0] || null;
      if (S.archive.model) sel.value = S.archive.model;
      S.archive.family = null;
      renderArchive();
    } catch (e) {
      $("#cards").removeAttribute("aria-busy");
      $("#cards").innerHTML = "";
      toast(e.message, true);
    }
  }

  function filtered(ignoreOutcome = false) {
    const A = S.archive, d = A.data;
    const res = A.model ? d.results[A.model] || {} : {};
    return d.tasks.filter((t) => {
      if (A.family && t.family !== A.family) return false;
      if (A.search && !t.id.toLowerCase().includes(A.search.toLowerCase())) return false;
      if (ignoreOutcome) return true;
      const r = res[t.id];
      if (A.outcome === "right" && !(r && r.correct)) return false;
      if (A.outcome === "wrong" && !(r && !r.correct && !r.error)) return false;
      return true;
    });
  }

  function renderArchive() {
    const A = S.archive, d = A.data;
    if (!d) return;
    const res = A.model ? d.results[A.model] || {} : {};

    // family chips with accuracy for the current model
    const chips = $("#family-chips");
    chips.innerHTML = "";
    const fams = [...new Set(d.tasks.map((t) => t.family))];
    const allChip = h("button", { class: "chip" + (A.family ? "" : " is-on") }, "All families");
    allChip.addEventListener("click", () => { A.family = null; renderArchive(); });
    chips.append(allChip);
    for (const f of fams) {
      const ts = d.tasks.filter((t) => t.family === f);
      const scored = ts.filter((t) => res[t.id] && !res[t.id].error);
      const acc = scored.length ? Math.round((100 * scored.filter((t) => res[t.id].correct).length) / scored.length) + "%" : "";
      const c = h("button", { class: "chip" + (A.family === f ? " is-on" : "") },
        d.family_labels[f] || f, acc ? h("span", { class: "chip-acc" }, acc) : null);
      c.addEventListener("click", () => { A.family = A.family === f ? null : f; renderArchive(); });
      chips.append(c);
    }

    const list = filtered();
    const scored = filtered(true).filter((t) => res[t.id] && !res[t.id].error);
    const right = scored.filter((t) => res[t.id].correct).length;
    const pct = scored.length ? (100 * right) / scored.length : 0;
    const suiteMeta = S.meta.suites.find((s) => s.name === A.suite);
    $("#archive-stats").innerHTML = `
      <span class="stat-big">${scored.length ? pct.toFixed(1) + "%" : "—"}</span>
      <span class="stat-bar"><span style="width:${pct}%"></span></span>
      <span>${A.model ? `<b>${esc(A.model)}</b>: ${right} of ${scored.length} answered correctly` : "no model results"} · ${list.length} task${list.length === 1 ? "" : "s"} shown</span>
      ${suiteMeta?.report ? `<a class="report-link" href="/suites/${encodeURIComponent(A.suite)}/report.html" target="_blank" rel="noopener">Open full report ↗</a>` : ""}`;

    const box = $("#cards");
    box.innerHTML = "";
    $("#archive-empty").hidden = list.length > 0;
    if (!list.length) $("#archive-empty").textContent = "No tasks match these filters.";
    const frag = document.createDocumentFragment();
    for (const t of list) {
      const r = res[t.id];
      const badge = !r || r.error ? "none" : r.correct ? "pass" : "fail";
      const keyTxt = t.answer_type === "number" ? `${fmtNum(t.answer)}${t.unit ? " " + t.unit : ""}` : t.answer;
      const ans = r && !r.error ? (t.answer_type === "number" ? fmtExact(r.parsed) : r.parsed ?? "—") : null;
      const card = h("button", { class: "card", "data-id": t.id, title: t.id },
        h("img", { src: `/thumb/${encodeURIComponent(A.suite)}/${encodeURIComponent(t.id)}.jpg`, loading: "lazy", alt: "",
                   onload: (e) => e.target.classList.add("loaded") }),
        h("span", { class: `card-badge ${badge}` }, badge === "pass" ? "✓" : badge === "fail" ? "✗" : "·"),
        h("div", { class: "card-body" },
          h("div", { class: "card-fam" }, d.family_labels[t.family] || t.family),
          h("div", { class: "card-id" }, t.id),
          h("div", { class: "card-key", html: `key <b>${esc(keyTxt)}</b>` }),
          h("div", { class: "card-ans", html: ans != null ? `model <span>${esc(ans)}</span>` : "model —" })));
      card.addEventListener("click", () => openDrawer(t.id));
      frag.append(card);
    }
    box.append(frag);
  }

  async function openDrawer(id) {
    const A = S.archive;
    const dr = $("#drawer");
    try {
      const d = await api(`/api/task?suite=${encodeURIComponent(A.suite)}&id=${encodeURIComponent(id)}`);
      const t = d.task;
      $("#dr-family").textContent = A.data.family_labels[t.family] || t.family;
      $("#dr-title").textContent = t.id;
      const num = t.answer_type === "number";
      const unit = t.unit ? " " + t.unit : "";
      const body = $("#drawer-body");
      const rows = Object.entries(d.answers).sort(([a], [b]) => BASELINES.includes(a) - BASELINES.includes(b)).map(([m, r]) => {
        const v = r.error ? "error" : r.parsed == null ? "—" : num ? fmtExact(r.parsed) : r.parsed;
        const err = num && r.err_tol_units != null ? fmtTol(r.err_tol_units) : "";
        return `<tr><td class="m">${esc(m)}${r.text && !BASELINES.includes(m) ? `<details><summary>reasoning</summary><pre>${esc(r.text)}</pre></details>` : ""}</td>
          <td>${esc(v)}</td><td class="${r.correct ? "ok" : "bad"}">${r.error ? "—" : r.correct ? "✓" : "✗"}</td><td>${err}</td></tr>`;
      }).join("");
      body.innerHTML = `
        <div class="dr-img viewport has-img loupe-on" id="dr-vp">
          <img id="dr-imgel" src="/suites/${encodeURIComponent(A.suite)}/${esc(t.image)}" alt="task image" draggable="false">
          <div class="loupe" id="dr-loupe"></div>
        </div>
        <p class="dr-q">${esc(t.question)}</p>
        <div class="dr-key"><span class="dk-label">Answer key</span>
          <span class="dk-val">${esc(num ? `${fmtNum(t.answer)} ± ${fmtNum(t.tolerance)}${unit}` : t.answer)}</span></div>
        <section class="dr-section"><h4>Answers</h4>
          ${rows ? `<table class="ans-table"><thead><tr><th>Model</th><th>Answer</th><th></th><th>Error</th></tr></thead><tbody>${rows}</tbody></table>` : `<p style="color:var(--ink-3)">No model has answered this suite yet.</p>`}
        </section>
        <section class="dr-section"><h4>Validator checks</h4><ul class="check-list" style="max-height:none">${(t.validation || []).map((c) =>
          `<li><span class="led ${c.passed ? "pass" : "fail"}"></span><span class="check-name">${esc(checkNameFor(c.name, t.family))}</span><span class="check-detail">${esc(c.detail)}</span></li>`).join("")}</ul></section>
        <section class="dr-section"><h4>Factors</h4><div class="factor-chips">${Object.entries(t.factors || {}).map(([k, v]) =>
          `<span>${esc(FACTOR_LABEL[k] || k)} <b>${esc(fmtFactor(k, v))}</b></span>`).join("")}
          ${t.meta?.level ? `<span>level <b>${t.meta.level}</b></span>` : ""}${t.meta?.sweep_factor ? `<span>sweep <b>${esc(t.meta.sweep_factor)}</b></span>` : ""}
          <span>seed <b>${t.seed}</b></span></div></section>`;
      attachLoupe($("#dr-vp"), $("#dr-imgel"), $("#dr-loupe"), () => true);
      dr.classList.add("is-open");
      dr.setAttribute("aria-hidden", "false");
      setTimeout(() => $(".icon-btn", dr).focus(), 50);
    } catch (e) { toast(e.message, true); }
  }
  function closeDrawer() {
    for (const dr of $$(".drawer.is-open")) {
      dr.classList.remove("is-open");
      dr.setAttribute("aria-hidden", "true");
    }
  }

  // ------------------------------------------------------------------ task pack download
  function download(name, href) {
    const a = h("a", { href, download: name });
    document.body.append(a); a.click(); a.remove();
  }
  function downloadPack() {
    const t = S.task;
    if (!t || !S.lastKey) return;
    const base = t.id;
    const pack = {
      id: t.id, family: t.family, question: t.question, answer_type: t.answer_type, choices: t.choices,
      unit: t.unit, answer: S.lastKey.answer, tolerance: S.lastKey.tolerance, factors: t.factors, seed: t.seed,
      validation: S.checksFull || t.checks, rejected_before_publish: t.rejected.map((r) => ({ attempt: r.attempt, reasons: r.reasons })),
      image: `${base}.png`, generator: `GaugeBench Studio ${S.meta.version}`,
    };
    download(`${base}.png`, t.image);
    const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" }));
    setTimeout(() => { download(`${base}.json`, url); setTimeout(() => URL.revokeObjectURL(url), 2000); }, 250);
    toast("Saved the image and task JSON.");
  }

  // ------------------------------------------------------------------ challenge
  // ------------------------------------------------------------------ sound (synthesised, no files)
  const SND = { on: store.get("gb-sound", true), ctx: null };
  function audio() {
    if (!SND.ctx) { try { SND.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (_) { SND.on = false; } }
    if (SND.ctx && SND.ctx.state === "suspended") SND.ctx.resume();
    return SND.ctx;
  }
  function tone(freq, dur, type = "sine", vol = 0.06, when = 0, slideTo = null) {
    const ctx = audio(); if (!ctx) return;
    const t0 = ctx.currentTime + when;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(ctx.destination); o.start(t0); o.stop(t0 + dur + 0.02);
  }
  function noise(dur, vol, freq) {
    const ctx = audio(); if (!ctx) return;
    const buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * dur), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    const src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    src.buffer = buf; f.type = "bandpass"; f.frequency.value = freq; g.gain.value = vol;
    src.connect(f).connect(g).connect(ctx.destination); src.start();
  }
  const sfx = {
    tick: () => SND.on && noise(0.02, 0.35, 3200),
    click: () => SND.on && (noise(0.04, 0.5, 1600), tone(150, 0.07, "square", 0.025)),
    stamp: () => SND.on && (tone(95, 0.2, "sine", 0.22, 0, 48), noise(0.07, 0.6, 500)),
    pass: () => SND.on && (tone(660, 0.12, "triangle", 0.06, 0.12), tone(990, 0.22, "triangle", 0.05, 0.22)),
    fail: () => SND.on && tone(196, 0.28, "sawtooth", 0.035, 0.12, 130),
    chime: () => SND.on && [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.3, "triangle", 0.045, i * 0.08)),
  };
  function setSound(on) {
    SND.on = on; store.set("gb-sound", on);
    const b = $("#btn-sound");
    b.setAttribute("aria-pressed", String(on));
    b.title = on ? "Sound on (M)" : "Sound off (M)";
    if (on) sfx.click();
  }

  // ------------------------------------------------------------------ confetti
  function confetti() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const cv = $("#confetti"), ctx = cv.getContext("2d");
    const W = (cv.width = innerWidth * devicePixelRatio), H = (cv.height = innerHeight * devicePixelRatio);
    const cols = ["#ff6b1a", "#ff8a45", "#7ea6ff", "#efebe2", "#39e07f", "#f5d33a"];
    const P = Array.from({ length: 160 }, () => ({
      x: W / 2 + (Math.random() - 0.5) * W * 0.25, y: H * 0.32, vx: (Math.random() - 0.5) * 22 * devicePixelRatio,
      vy: (-Math.random() * 20 - 6) * devicePixelRatio, w: (4 + Math.random() * 6) * devicePixelRatio, h: (8 + Math.random() * 10) * devicePixelRatio,
      r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: cols[(Math.random() * cols.length) | 0], needle: Math.random() < 0.2,
    }));
    const t0 = performance.now();
    (function frame(t) {
      const age = t - t0;
      ctx.clearRect(0, 0, W, H);
      for (const p of P) {
        p.vy += 0.55 * devicePixelRatio; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.globalAlpha = Math.max(0, 1 - age / 2200);
        ctx.fillStyle = p.c;
        if (p.needle) { ctx.beginPath(); ctx.moveTo(0, -p.h); ctx.lineTo(p.w / 3, p.h / 2); ctx.lineTo(-p.w / 3, p.h / 2); ctx.fill(); }
        else ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (age < 2300) requestAnimationFrame(frame); else ctx.clearRect(0, 0, W, H);
    })(t0);
  }

  // ------------------------------------------------------------------ your record + rank
  const RANKS = [[0, "Apprentice"], [40, "Technician"], [60, "Senior technician"], [75, "Calibration engineer"], [90, "Metrologist"]];
  const getHistory = () => store.get("gb-history", []);
  function rankOf(hist) {
    const recent = hist.slice(-60);
    if (recent.length < 5) return { idx: -1, name: "Trainee", acc: null, need: 5 - recent.length };
    const acc = (100 * recent.reduce((s, e) => s + (e.c ? (e.h ? 0.5 : 1) : 0), 0)) / recent.length;
    let idx = 0;
    RANKS.forEach(([min], i) => { if (acc >= min) idx = i; });
    return { idx, name: RANKS[idx][1], acc, next: RANKS[idx + 1] };
  }
  function currentStreak(hist) {
    let s = 0;
    for (let i = hist.length - 1; i >= 0 && hist[i].c; i--) s++;
    return s;
  }
  function record(entry) {
    const hist = getHistory();
    const before = rankOf(hist);
    hist.push({ ...entry, t: Date.now() });
    if (hist.length > 600) hist.splice(0, hist.length - 600);
    store.set("gb-history", hist);
    const after = rankOf(hist);
    renderTally();
    if (after.idx > before.idx && after.idx >= 0) {
      setTimeout(() => { toast(`Rank up: you're now a ${after.name}!`); confetti(); sfx.chime(); }, 700);
    }
    const st = currentStreak(hist);
    if (entry.c && st > 0 && st % 5 === 0) setTimeout(() => { toast(`${st} in a row. Sharp eyes!`); sfx.chime(); }, 600);
  }

  function openRecord() {
    const hist = getHistory();
    const rk = rankOf(hist);
    const body = $("#record-body");
    const n = hist.length, right = hist.filter((e) => e.c).length, hinted = hist.filter((e) => e.h).length;
    const best = (() => { let b = 0, s = 0; for (const e of hist) { s = e.c ? s + 1 : 0; b = Math.max(b, s); } return b; })();
    const acc = rk.acc ?? (n ? (100 * right) / n : 0);
    const C2 = 2 * Math.PI * 52, frac = Math.min(1, acc / 100);
    const byFam = {};
    for (const e of hist) { (byFam[e.f] ||= [0, 0]); byFam[e.f][1]++; if (e.c) byFam[e.f][0]++; }
    const label = (f) => S.meta.families.find((x) => x.id === f)?.label || f;
    const wrongNum = hist.filter((e) => !e.c && e.tu != null);
    const near = wrongNum.filter((e) => e.tu <= 2).length, wild = wrongNum.filter((e) => e.tu > 20).length;
    const nextTxt = rk.idx < 0 ? `Answer ${rk.need} more task${rk.need === 1 ? "" : "s"} to get ranked.`
      : rk.next ? `${(rk.next[0] - acc).toFixed(0)} points of accuracy to ${rk.next[1]}.` : "Top rank. Nothing left to prove.";
    body.innerHTML = n === 0 ? `<p class="rec-empty">No readings yet. Answer a task on the Bench, play the Daily, or take on the Challenge, and your record builds up here.</p>` : `
      <div class="rec-hero">
        <svg class="rec-dial" viewBox="0 0 132 132" aria-label="Recent accuracy ${acc.toFixed(0)}%">
          <circle class="rd-track" cx="66" cy="66" r="52" stroke-dasharray="${C2 * 0.75} ${C2}" transform="rotate(135 66 66)"/>
          <circle class="rd-fill" cx="66" cy="66" r="52" stroke-dasharray="${C2 * 0.75} ${C2}" stroke-dashoffset="${C2 * 0.75}" transform="rotate(135 66 66)" id="rd-fill"/>
          <line class="rd-needle" id="rd-needle" x1="66" y1="66" x2="66" y2="26" style="transform: rotate(-135deg)"/>
          <circle cx="66" cy="66" r="5" fill="var(--accent)"/>
          <text x="66" y="104" text-anchor="middle" font-size="18">${acc.toFixed(0)}%</text>
        </svg>
        <div>
          <div class="dr-kicker">Current rank</div>
          <div class="rec-rank">${esc(rk.name)}</div>
          <div class="rec-next">${nextTxt}</div>
          ${rk.idx >= 0 && rk.next ? `<div class="rec-bar"><span style="width:${Math.max(4, ((acc - RANKS[rk.idx][0]) / (rk.next[0] - RANKS[rk.idx][0])) * 100)}%"></span></div>` : ""}
        </div>
      </div>
      <div class="rec-grid">
        <div><b>${n}</b><span>Readings</span></div>
        <div><b>${n ? Math.round((100 * right) / n) : 0}%</b><span>All-time</span></div>
        <div><b>${best}</b><span>Best streak</span></div>
        <div><b>${hinted}</b><span>Hints used</span></div>
      </div>
      <section class="dr-section"><h4>By instrument</h4><div class="fam-bars">${Object.entries(byFam).sort((a, b) => b[1][1] - a[1][1]).map(([f, [c, t]]) =>
        `<div class="fam-bar"><span>${esc(label(f))}</span><span class="fb-track"><span style="width:${(100 * c) / t}%"></span></span><span class="fb-n">${c}/${t}</span></div>`).join("")}</div></section>
      ${wrongNum.length ? `<section class="dr-section"><h4>When you miss a number</h4><p class="rec-next">${near} of ${wrongNum.length} were near misses (within 2× the tolerance)${wild ? ` and ${wild} were way off (over 20×, usually a missed multiplier or the wrong scale)` : ""}. ${near >= wrongNum.length / 2 ? "Like the models, you snap to the nearest tick. Try the loupe." : "Check the multiplier and which ring you're reading."}</p></section>` : ""}
      <section class="dr-section"><h4>Last ${Math.min(40, n)} readings</h4><div class="recent">${hist.slice(-40).map((e) => `<i class="${e.c ? (e.h ? "hint" : "ok") : "no"}" title="${esc(label(e.f))}"></i>`).join("")}</div></section>
      <button class="ghost-dark rec-reset" id="rec-reset">Reset my record</button>`;
    const dr = $("#record");
    dr.classList.add("is-open"); dr.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const f = $("#rd-fill"), nd = $("#rd-needle");
      if (f) f.setAttribute("stroke-dashoffset", String(C2 * 0.75 * (1 - frac)));
      if (nd) nd.style.transform = `rotate(${-135 + 270 * frac}deg)`;
    }));
    $("#rec-reset")?.addEventListener("click", () => {
      if (!confirm("Reset your whole record? This can't be undone.")) return;
      store.set("gb-history", []); renderTally(); openRecord();
    });
  }

  // ------------------------------------------------------------------ hints
  async function getHint(where) {
    const bench = where === "bench";
    const t = bench ? S.task : C.tasks[C.i];
    if (!t) return;
    if (bench ? S.answered : !$("#ch-result").hidden) return;
    try {
      const r = await api("/api/hint", bench || C.mode === "daily" ? { id: t.id } : { id: t.id, suite: C.suite });
      const box = bench ? $("#ticket-hint") : $("#ch-hint-box");
      box.hidden = false;
      box.innerHTML = `<span class="callout-icon" aria-hidden="true">?</span><div><b>Hint.</b> ${esc(r.hint)}</div>`;
      if (bench) S.hinted = true; else C.hinted[C.i] = true;
      (bench ? $("#btn-hint") : $("#ch-hint")).disabled = true;
      sfx.tick();
    } catch (e) { handleErr(e); }
  }

  // ------------------------------------------------------------------ rounds engine (Challenge + Daily)
  const C = { mode: "challenge", suite: null, model: null, n: 10, family: "", tasks: [], i: 0, you: 0, gem: 0, log: [], hinted: [],
              t0: 0, timer: null, total: 0, choice: null, done: false };
  let challengeReady = false;

  function initChallenge() {
    const suites = S.meta.suites.filter((s) => s.models.some((m) => !BASELINES.includes(m)));
    if (!suites.length) {
      $("#ch-start").disabled = true;
      $("#ch-empty").hidden = false;
      $("#ch-empty").textContent = S.meta.public ? "No recorded model answers are available on this server yet."
        : "No suite has model results yet. Evaluate one first, e.g. python -m gaugebench evaluate runs/sample --model gemini:gemini-3.5-flash-lite";
      return;
    }
    const seg = $("#ch-suite");
    seg.innerHTML = "";
    const pick = suites.reduce((a, b) => (b.tasks > a.tasks ? b : a));
    for (const s of suites) {
      const b = h("button", { "data-suite": s.name }, s.name, h("span", { class: "seg-n" }, String(s.tasks)));
      b.addEventListener("click", () => chooseSuite(s.name));
      seg.append(b);
    }
    $$("#ch-n button").forEach((b) => b.addEventListener("click", () => {
      C.n = Number(b.dataset.n);
      $$("#ch-n button").forEach((x) => x.classList.toggle("is-on", x === b));
    }));
    $("#ch-model").addEventListener("change", (e) => (C.model = e.target.value));
    $("#ch-family").addEventListener("change", (e) => (C.family = e.target.value));
    $("#ch-start").addEventListener("click", startChallenge);
    chooseSuite(pick.name);
  }

  async function chooseSuite(name) {
    C.suite = name;
    $$("#ch-suite button").forEach((b) => b.classList.toggle("is-on", b.dataset.suite === name));
    const s = S.meta.suites.find((x) => x.name === name);
    const real = s.models.filter((m) => !BASELINES.includes(m));
    const sel = $("#ch-model");
    sel.innerHTML = "";
    for (const m of [...real, ...s.models.filter((m) => BASELINES.includes(m))]) sel.append(h("option", { value: m }, modelLabel(m)));
    C.model = real[0] || s.models[0];
    sel.value = C.model;
    try {
      const d = await api(`/api/suite?name=${encodeURIComponent(name)}`);
      const fams = [...new Set(d.tasks.map((t) => t.family))];
      const fs = $("#ch-family");
      fs.innerHTML = `<option value="">All instruments (mixed)</option>` + fams.map((f) => `<option value="${esc(f)}">${esc(d.family_labels[f] || f)}</option>`).join("");
      C.family = "";
    } catch (e) { toast(e.message, true); }
  }

  async function startChallenge() {
    try {
      const d = await api("/api/challenge/start", { suite: C.suite, model: C.model, n: C.n, family: C.family });
      C.mode = "challenge";
      startRounds(d.tasks);
    } catch (e) { toast(e.message, true); }
  }

  function startRounds(tasks) {
    Object.assign(C, { tasks, i: 0, you: 0, gem: 0, log: [], hinted: [], total: 0, done: false });
    const daily = C.mode === "daily";
    $(".scoreboard").classList.toggle("solo", daily);
    $("#sb-model").textContent = daily ? `Daily #${dailyNumber()}` : C.model.replace(/^gemini-/, "Gemini ").replace(/^claude-/, "Claude ");
    $("#sb-you").textContent = "0"; $("#sb-gem").textContent = daily ? "" : "0";
    $("#ch-end").hidden = true;
    $("#ch-play").hidden = false;
    setView("play");
    renderRound();
  }

  function renderPips() {
    const p = $("#pips");
    p.innerHTML = "";
    const daily = C.mode === "daily";
    C.tasks.forEach((_, k) => {
      const l = C.log[k];
      p.append(h("span", { class: "pip" + (daily ? " solo" : "") + (k === C.i && !C.done ? " now" : ""), title: `round ${k + 1}` },
        h("i", { class: "y" + (l ? (l.you ? (l.hint ? " hint" : " ok") : " no") : "") }),
        daily ? null : h("i", { class: "g" + (l ? (l.gem ? " ok" : " no") : "") })));
    });
  }

  function renderRound() {
    const t = C.tasks[C.i];
    C.choice = null;
    $("#sb-round").textContent = `Round ${C.i + 1} / ${C.tasks.length}` + (C.mode === "daily" ? ` · L${C.i + 1}` : "");
    $("#ch-kicker").textContent = `Round ${C.i + 1}`;
    $("#ch-family-label").textContent = t.family_label;
    $("#ch-q").textContent = t.question;
    const img = $("#ch-img");
    img.src = t.image;
    const vp = $("#ch-vp");
    vp.classList.remove("has-img"); void vp.offsetWidth; vp.classList.add("has-img");
    $("#ch-result").hidden = true;
    $("#ch-hint-box").hidden = true;
    $("#ch-form").hidden = false;
    $$("#ch-form input, #ch-form button").forEach((el) => (el.disabled = false));
    const num = t.answer_type === "number";
    $("#ch-num").hidden = !num;
    const ch = $("#ch-choices");
    ch.hidden = num;
    ch.innerHTML = "";
    if (num) {
      $("#ch-input").value = "";
      $("#ch-unit").textContent = t.unit || "";
      setTimeout(() => $("#ch-input").focus({ preventScroll: true }), 50);
    } else {
      t.choices.forEach((c) => {
        const b = h("button", { type: "button", class: "choice", role: "radio", "aria-checked": "false" }, c);
        b.addEventListener("click", () => { C.choice = c; $$(".choice", ch).forEach((x) => x.setAttribute("aria-checked", String(x === b))); });
        ch.append(b);
      });
    }
    renderPips();
    C.t0 = Date.now();
    clearInterval(C.timer);
    const tick = () => {
      const s = Math.floor((Date.now() - C.t0) / 1000);
      $("#ch-clock").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    tick();
    C.timer = setInterval(tick, 500);
  }

  async function submitRound(e) {
    e?.preventDefault();
    const t = C.tasks[C.i];
    if (!t || !$("#ch-result").hidden) return;
    const raw = t.answer_type === "number" ? $("#ch-input").value.trim().replace(",", ".") : C.choice;
    if (raw == null || raw === "") { toast(t.answer_type === "number" ? "Type your answer first." : "Pick an option first."); return; }
    const daily = C.mode === "daily";
    try {
      const r = daily ? await api("/api/answer", { id: t.id, answer: raw })
        : await api("/api/challenge/answer", { suite: C.suite, model: C.model, id: t.id, answer: raw });
      clearInterval(C.timer);
      const secs = (Date.now() - C.t0) / 1000;
      C.total += secs;
      const you = r.score.correct, gem = daily ? null : r.model.correct;
      const hint = !!C.hinted[C.i];
      C.log[C.i] = { id: t.id, family: t.family_label, fam: t.family, you, gem, hint, secs, modelSecs: daily ? null : r.model.latency_s };
      record({ f: t.family, c: you, tu: r.score.err_tol_units ?? null, h: hint, m: C.mode });
      sfx.stamp(); (you ? sfx.pass : sfx.fail)();
      if (you) { C.you++; bumpScore("#sb-you", C.you); }
      if (gem) { C.gem++; bumpScore("#sb-gem", C.gem); }
      $$("#ch-form input, #ch-form button").forEach((el) => (el.disabled = true));
      $("#ch-form").hidden = true;
      const num = r.key.answer_type === "number";
      const unit = r.key.unit ? " " + r.key.unit : "";
      const fmt = (v) => (v == null ? "no answer" : num ? fmtExact(v) + unit : v);
      const keyTxt = num ? `${fmtNum(r.key.answer)} ± ${fmtNum(r.key.tolerance)}${unit}` : r.key.answer;
      const call = daily ? (you ? (hint ? "Correct, with a hint." : "Correct. Clean read.") : "Not this time. Compare your reading with the key.")
        : you && !gem ? "You read it right where the model failed."
        : !you && gem ? "The model got this one. Look again with the loupe."
        : you && gem ? "Both correct." : "Both wrong. A hard one.";
      const last = C.i === C.tasks.length - 1;
      const res = $("#ch-result");
      res.hidden = false;
      res.innerHTML = `
        <div class="ch-row"><span class="who">You</span><span class="val">${esc(fmt(r.score.parsed))}${hint ? ' <span class="hint-tag">hint</span>' : ""}</span><span class="mark ${you ? "ok" : "no"}">${you ? "✓" : "✗"}</span></div>
        ${daily ? "" : `<div class="ch-row"><span class="who">Model</span><span class="val">${esc(fmt(r.model.parsed))}</span><span class="mark ${gem ? "ok" : "no"}">${gem ? "✓" : "✗"}</span></div>`}
        <div class="ch-row key"><span class="who">Key</span><span class="val">${esc(keyTxt)}</span><span></span></div>
        <p class="ch-callout">${call}</p>
        ${!daily && r.model.text ? `<details><summary>Model's reasoning</summary><pre>${esc(r.model.text)}</pre></details>` : ""}
        <button class="btn btn-ink ch-next" id="ch-next">${last ? "See final score" : "Next round"} <kbd>↵</kbd></button>`;
      $("#ch-next").addEventListener("click", nextRound);
      scrollOnPhone(res);
      setTimeout(() => $("#ch-next").focus({ preventScroll: true }), 30);
      renderPips();
    } catch (err) {
      if (err.data?.code === "task_expired") { toast("These rounds expired when the app restarted. Start again.", true); endRounds(true); return; }
      toast(err.message, true);
    }
  }

  function bumpScore(sel, v) {
    const el = $(sel);
    el.textContent = String(v);
    el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");
  }

  function nextRound() {
    if (C.i < C.tasks.length - 1) { C.i++; renderRound(); }
    else endRounds(false);
  }

  function endRounds(quit) {
    clearInterval(C.timer);
    C.done = true;
    const played = C.log.filter(Boolean);
    const back = C.mode === "daily" ? "daily" : "challenge";
    if (quit && !played.length) { $("#ch-play").hidden = true; setView(back); return; }
    if (C.mode === "daily") { if (!quit) finishDaily(); $("#ch-play").hidden = true; setView("daily"); return; }
    $("#ch-play").hidden = true;
    const end = $("#ch-end");
    end.hidden = false;
    const n = played.length;
    const ms = played.map((l) => l.modelSecs).filter((x) => x != null);
    const avgModel = ms.length ? ms.reduce((a, b) => a + b, 0) / ms.length : null;
    const win = C.you > C.gem;
    const verdict = win ? "You out-read the machine." : C.you < C.gem ? "The machine wins this round." : "Dead heat.";
    end.innerHTML = `
      <div class="end-card">
        <div class="end-kicker">${quit ? "Challenge ended early" : "Final score"} · ${n} round${n === 1 ? "" : "s"}</div>
        <div class="end-score"><span class="sb-score" style="color:var(--accent)">${C.you}</span><span class="end-vs">VS</span><span class="sb-score" style="color:var(--blue)">${C.gem}</span></div>
        <div class="end-who"><span>You</span><span>${esc(C.model)}</span></div>
        <div class="end-verdict">${verdict}</div>
        <p class="end-sub">You averaged ${(C.total / Math.max(1, n)).toFixed(1)} s per task${avgModel != null ? `; the model took ${avgModel.toFixed(1)} s` : ""}. Same images, same tolerance.</p>
        <div class="end-actions">
          <button class="big-button" id="end-again"><span class="bb-cap">Play again</span></button>
          <button class="ghost-dark" id="end-setup">Change settings</button>
        </div>
      </div>
      <div class="end-list">${played.map((l) => `
        <div class="end-item"><img src="/thumb/${encodeURIComponent(C.suite)}/${encodeURIComponent(l.id)}.jpg" alt="">
          <div><div class="ei-fam">${esc(l.family)}</div>
          <div class="ei-res">you <span class="${l.you ? "ok" : "no"}">${l.you ? "✓" : "✗"}</span> · model <span class="${l.gem ? "ok" : "no"}">${l.gem ? "✓" : "✗"}</span></div></div></div>`).join("")}
      </div>`;
    $("#end-again").addEventListener("click", startChallenge);
    $("#end-setup").addEventListener("click", () => { end.hidden = true; setView("challenge"); });
    if (win && !quit) { confetti(); sfx.chime(); }
  }

  // ------------------------------------------------------------------ GaugeBench Daily
  const DAILY_EPOCH = Date.UTC(2026, 10, 23);
  const dateKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const dailyNumber = (d = new Date()) => Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) - DAILY_EPOCH) / 864e5) + 1;
  function fnv(str) { let x = 0x811c9dc5; for (const ch of str) { x ^= ch.charCodeAt(0); x = Math.imul(x, 0x01000193) >>> 0; } return x >>> 0; }
  function dailyPlan(key = dateKey()) {
    let s = fnv(`gaugebench-daily:${key}`);
    const rnd = () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const fams = S.meta.families.map((f) => f.id);
    for (let i = fams.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [fams[i], fams[j]] = [fams[j], fams[i]]; }
    return fams.slice(0, 5).map((f, i) => ({ family: f, level: i + 1, seed: fnv(`${key}:${i}:${f}`) }));
  }
  const dailyStore = () => store.get("gb-daily", { results: {}, streak: 0, best: 0, last: null });
  function shareText(res, n) {
    const sq = res.grid.map((g) => (g === "ok" ? "🟧" : g === "hint" ? "🟨" : "⬛")).join("");
    return `GaugeBench Daily #${n} · ${res.score}/5\n${sq}\nL1 → L5 · read the gauge, beat the glare`;
  }

  let dailyTimer;
  function renderDaily() {
    const key = dateKey(), n = dailyNumber(), plan = dailyPlan(key);
    const ds = dailyStore(), res = ds.results[key];
    const label = (f) => S.meta.families.find((x) => x.id === f)?.label || f;
    const played = Object.keys(ds.results).length;
    const avg = played ? (Object.values(ds.results).reduce((a, r) => a + r.score, 0) / played).toFixed(1) : "–";
    const nice = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    $("#daily-card").innerHTML = `
      <div class="dly-top">
        <div>
          <div class="dly-kicker">GaugeBench Daily</div>
          <h1 class="dly-title">Five gauges.<br>One shot.</h1>
          <p class="dly-sub">The same five instruments for everyone today, from a clean L1 to a brutal L5. Hints are allowed but they show on your result.</p>
        </div>
        <div class="dly-date"><b>#${n}</b>${esc(nice)}</div>
      </div>
      <div class="dly-rounds">${plan.map((p, i) => {
        const g = res ? res.grid[i] : "";
        return `<div class="dly-round ${g}"><svg viewBox="0 0 32 32" aria-hidden="true">${FAMILY_ICONS[p.family] || ""}</svg>
          <span class="dr-name">${esc(label(p.family))}</span><span class="dr-lvl">L${p.level}</span></div>`; }).join("")}</div>
      <div class="dly-stats">
        <div class="dly-stat"><b>${ds.streak || 0}${ds.streak >= 2 ? " 🔥" : ""}</b><span>Day streak</span></div>
        <div class="dly-stat"><b>${ds.best || 0}</b><span>Best streak</span></div>
        <div class="dly-stat"><b>${played}</b><span>Played</span></div>
        <div class="dly-stat"><b>${avg}</b><span>Avg score</span></div>
      </div>
      ${res ? `
        <div class="dly-actions">
          <div class="dly-share" id="dly-share">
            <div class="ds-head">GaugeBench Daily #${n} · <b>${res.score}/5</b></div>
            <div class="ds-tiles">${res.grid.map((g, i) => `<span class="ds-tile ${g}" title="L${i + 1}">L${i + 1}</span>`).join("")}</div>
            <div class="ds-foot">${res.score === 5 ? "Perfect read." : res.score >= 3 ? "Steady hands." : "The gauges won today."}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px">
            <button class="btn btn-blue" id="dly-copy" style="width:auto">Copy result</button>
            <div class="dly-next">Next daily in <b id="dly-count">--:--:--</b></div>
          </div>
        </div>` : `
        <div class="dly-actions">
          <button class="big-button" id="dly-start"><span class="bb-cap">Start today's daily</span></button>
          <span class="dly-next" id="dly-prep"></span>
        </div>`}`;
    $("#daily-dot").hidden = !!res;
    if (res) {
      $("#dly-copy").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(shareText(res, n)); toast("Result copied. Paste it anywhere."); }
        catch (_) { window.prompt("Copy your result:", shareText(res, n)); }
      });
      clearInterval(dailyTimer);
      const tick = () => {
        const now = new Date(), mid = new Date(now); mid.setHours(24, 0, 0, 0);
        const s = Math.max(0, Math.floor((mid - now) / 1000));
        const el = $("#dly-count");
        if (!el) { clearInterval(dailyTimer); return; }
        el.textContent = `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
        if (s === 0) renderDaily();
      };
      tick(); dailyTimer = setInterval(tick, 1000);
    } else {
      $("#dly-start").addEventListener("click", startDaily);
    }
  }

  async function startDaily() {
    const btn = $("#dly-start"), prep = $("#dly-prep");
    btn.disabled = true;
    const plan = dailyPlan();
    const tasks = [];
    try {
      for (let i = 0; i < plan.length; i++) {
        prep.textContent = `Preparing today's gauges ${i + 1}/5…`;
        const p = plan[i];
        const t = await api("/api/generate", { family: p.family, level: p.level, seed: String(p.seed), factors: {} });
        tasks.push({ id: t.id, family: t.family, family_label: t.family_label, question: t.question, answer_type: t.answer_type,
                     choices: t.choices, unit: t.unit, image: t.image });
      }
      C.mode = "daily";
      sfx.click();
      startRounds(tasks);
    } catch (e) {
      toast(e.message, true);
      btn.disabled = false; prep.textContent = "";
    }
  }

  function finishDaily() {
    const key = dateKey(), ds = dailyStore();
    if (ds.results[key]) return;
    const grid = C.tasks.map((_, i) => { const l = C.log[i]; return !l ? "no" : l.you ? (l.hint ? "hint" : "ok") : "no"; });
    const score = grid.filter((g) => g !== "no").length;
    ds.results[key] = { score, grid };
    const y = new Date(); y.setDate(y.getDate() - 1);
    ds.streak = ds.last === dateKey(y) ? (ds.streak || 0) + 1 : 1;
    ds.best = Math.max(ds.best || 0, ds.streak);
    ds.last = key;
    store.set("gb-daily", ds);
    renderDaily();
    if (score >= 4) { setTimeout(() => { confetti(); sfx.chime(); }, 250); }
    toast(score === 5 ? "Perfect daily! 5 out of 5." : `Daily done: ${score}/5. Come back tomorrow.`);
  }

  // ------------------------------------------------------------------ help + tabs
  function openHelp() { $("#help").hidden = false; }
  function closeHelp() { $("#help").hidden = true; }
  function moveTabIndicator() {
    const a = $(".tab.is-active"), ind = $(".tab-ind");
    if (!a || !ind) return;
    ind.style.width = `${a.offsetWidth}px`;
    ind.style.transform = `translateX(${a.offsetLeft}px)`;
  }

  // ------------------------------------------------------------------ views + keys
  let archiveReady = false;
  const VIEWS = ["bench", "daily", "challenge", "archive", "play"];
  function setView(v) {
    const tab = v === "play" ? C.mode : v;
    $$(".tab").forEach((t) => { const on = t.dataset.view === tab; t.classList.toggle("is-active", on); t.setAttribute("aria-selected", String(on)); });
    for (const name of VIEWS) $(`#view-${name}`).hidden = name !== v;
    if (v === "archive" && !archiveReady) { archiveReady = true; initArchive(); }
    if (v === "challenge" && !challengeReady) { challengeReady = true; initChallenge(); }
    if (v === "challenge") { $("#ch-setup").hidden = false; }
    if (v === "daily") renderDaily();
    if (v !== "play") store.set("gb-view", v);
    moveTabIndicator();
    window.scrollTo({ top: 0 });
  }

  function onTab(v) {
    if (!$("#view-play").hidden && !C.done && C.log.filter(Boolean).length && !confirm("Leave this game? Your progress in it will be lost.")) return;
    clearInterval(C.timer);
    sfx.tick();
    setView(v);
  }

  function wire() {
    $$(".tab").forEach((t) => t.addEventListener("click", () => onTab(t.dataset.view)));
    $("#btn-generate").addEventListener("click", () => { sfx.click(); generate(); });
    $("#answer-form").addEventListener("submit", submitAnswer);
    $("#btn-reveal").addEventListener("click", reveal);
    $("#btn-hint").addEventListener("click", () => getHint("bench"));
    $("#ch-hint").addEventListener("click", () => getHint("round"));
    $("#ch-form").addEventListener("submit", submitRound);
    $("#ch-quit").addEventListener("click", () => endRounds(true));
    attachLoupe($("#ch-vp"), $("#ch-img"), $("#ch-loupe"), () => true);
    $("#btn-ask").addEventListener("click", askGemini);
    $("#btn-pack").addEventListener("click", downloadPack);
    $("#btn-link").addEventListener("click", copyLink);
    $("#btn-next").addEventListener("click", () => { sfx.click(); generate(); });
    $("#btn-record").addEventListener("click", openRecord);
    $("#btn-sound").addEventListener("click", () => setSound(!SND.on));
    $("#btn-help").addEventListener("click", openHelp);
    $$("[data-close-help]").forEach((el) => el.addEventListener("click", closeHelp));
    $("#btn-clean").addEventListener("click", () => { setFactors(S.meta.base); toast("All knobs back to the clean baseline."); });
    $$(".preset").forEach((b) => b.addEventListener("click", () => { sfx.click(); generate(Number(b.dataset.level)); }));
    $("#btn-seed-lock").addEventListener("click", (e) => {
      S.seedLocked = !S.seedLocked;
      e.currentTarget.setAttribute("aria-pressed", String(S.seedLocked));
      if (S.seedLocked && !$("#seed").value && S.task) $("#seed").value = S.task.seed;
      if (!S.seedLocked) $("#seed").value = "";
    });
    $("#tg-vision").addEventListener("change", (e) => {
      $("#viewport").classList.toggle("vision-on", e.target.checked);
      if (S.task) $("#task-img").src = e.target.checked ? S.task.vision : S.task.image;
      sfx.tick();
    });
    $("#tg-loupe").addEventListener("change", (e) => { $("#viewport").classList.toggle("loupe-on", e.target.checked); sfx.tick(); });
    $("#viewport").classList.add("loupe-on");
    attachLoupe($("#viewport"), $("#task-img"), $("#loupe"), () => $("#tg-loupe").checked);

    $("#model-select").addEventListener("change", (e) => { S.archive.model = e.target.value; renderArchive(); });
    $$("#outcome-seg button").forEach((b) => b.addEventListener("click", () => {
      S.archive.outcome = b.dataset.outcome;
      $$("#outcome-seg button").forEach((x) => x.classList.toggle("is-on", x === b));
      renderArchive();
    }));
    let st;
    $("#search").addEventListener("input", (e) => { clearTimeout(st); st = setTimeout(() => { S.archive.search = e.target.value.trim(); renderArchive(); }, 150); });
    $$("[data-close]").forEach((el) => el.addEventListener("click", closeDrawer));
    window.addEventListener("resize", () => {
      moveTabIndicator();
      if (S.lastKey && S.lastKey.answer_type === "number" && !$("#verdict").hidden) drawStrip($("#strip"), S.lastKey, S.lastYou, S.lastGem?.parsed);
    });
    document.fonts?.ready.then(moveTabIndicator);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeDrawer(); closeHelp(); return; }
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (e.key === "?") { e.preventDefault(); $("#help").hidden ? openHelp() : closeHelp(); return; }
      if (k === "m") { setSound(!SND.on); return; }
      if (k === "r") { openRecord(); return; }
      if (!$("#view-play").hidden) {
        const t = C.tasks[C.i];
        if (!t || C.done) return;
        if (k === "h") { getHint("round"); return; }
        if (e.key === "Enter" && $("#ch-result").hidden && t.answer_type === "choice") { e.preventDefault(); submitRound(); }
        else if (/^[1-9]$/.test(e.key) && $("#ch-result").hidden && t.answer_type === "choice") { const b = $$("#ch-choices .choice")[Number(e.key) - 1]; if (b) b.click(); }
        return;
      }
      if ($("#view-bench").hidden) return;
      if (k === "g") { e.preventDefault(); sfx.click(); generate(); }
      else if (k === "h") getHint("bench");
      else if (k === "l") { const c = $("#tg-loupe"); c.checked = !c.checked; c.dispatchEvent(new Event("change")); }
      else if (k === "v") { const c = $("#tg-vision"); c.checked = !c.checked; c.dispatchEvent(new Event("change")); }
      else if (/^[1-9]$/.test(k) && S.task && S.task.answer_type === "choice" && !S.answered) {
        const b = $$(".choice")[Number(k) - 1];
        if (b) b.click();
      } else if (k === "enter" && S.task && S.task.answer_type === "choice" && !S.answered) submitAnswer();
    });
  }

  // ------------------------------------------------------------------ shareable task links
  function taskLink() {
    const t = S.task;
    const p = new URLSearchParams({ family: t.family, seed: String(t.seed) });
    for (const [k, v] of Object.entries(t.factors)) if (String(S.meta.base[k]) !== String(v)) p.set(k, String(v));
    return `${location.origin}/?${p}`;
  }
  async function copyLink() {
    if (!S.task) return;
    const url = taskLink();
    try { await navigator.clipboard.writeText(url); toast("Link copied: it recreates exactly this task."); }
    catch (_) { window.prompt("Copy this link:", url); }
  }
  function applyUrl() {
    const p = new URLSearchParams(location.search);
    const view = p.get("view");
    const fam = p.get("family");
    if (fam && S.meta.families.some((f) => f.id === fam)) {
      selectFamily(fam);
      const f = {};
      for (const k of Object.keys(S.meta.factors)) if (p.has(k)) f[k] = p.get(k);
      setFactors({ ...S.meta.base, ...f });
      if (/^\d+$/.test(p.get("seed") || "")) {
        $("#seed").value = p.get("seed");
        S.seedLocked = true;
        $("#btn-seed-lock").setAttribute("aria-pressed", "true");
      }
      setView("bench");
      generate();
      return true;
    }
    if (["bench", "daily", "challenge", "archive"].includes(view)) { setView(view); return true; }
    return false;
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    try {
      S.meta = await api("/api/meta");
    } catch (e) {
      toast(e.message, true);
      return;
    }
    buildRack();
    selectFamily(S.family);
    renderTally();
    wire();
    const b = $("#btn-sound");                       // reflect the saved preference without a click sound
    b.setAttribute("aria-pressed", String(SND.on));
    b.title = SND.on ? "Sound on (M)" : "Sound off (M)";
    $("#daily-dot").hidden = !!dailyStore().results[dateKey()];
    if (!applyUrl()) setView(store.get("gb-view", "bench"));
  }
  boot();
})();
