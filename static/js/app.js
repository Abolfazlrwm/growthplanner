/* رشد شخصی — small, dependency-free UI layer on top of HTMX.
   Everything here reacts to a user action (theme, menu, toast, task change). */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  // Interface language (set by the server on <html lang>); window.I18N holds the English strings.
  var LANG = (doc.documentElement.lang || "fa").slice(0, 2);
  var I18N = window.I18N || {};
  function T(text) { return LANG === "en" && I18N[text] ? I18N[text] : text; }
  function tf(key, args) {
    var i = 0;
    return T(key).replace(/\{d\}|\{\}/g, function () { return args[i++]; });
  }
  window.growthT = T; window.growthTf = tf;
  function cssVar(name, fallback) {
    var v = getComputedStyle(doc.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function faDigits(value) {
    if (LANG === "en") return String(value);
    return String(value).replace(/\d/g, function (d) { return FA_DIGITS[d]; });
  }
  function haptic(ms) {
    try { if (navigator.vibrate) navigator.vibrate(ms || 10); } catch (e) { /* not supported */ }
  }

  /* ---------- Appearance: light / dark / auto, colour palette, language ---------- */
  function getMode() {
    try { var m = localStorage.getItem("theme"); return m === "dark" || m === "light" ? m : "auto"; } catch (e) { return "auto"; }
  }
  function systemDark() { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches); }
  function setCookie(name, value) {
    doc.cookie = name + "=" + encodeURIComponent(value) + ";path=/;max-age=31536000;samesite=lax";
  }
  function syncAppearanceUi() {
    var mode = getMode(), dark = root.classList.contains("dark"), pal = root.dataset.palette || "tile";
    doc.querySelectorAll("[data-theme-toggle]").forEach(function (btn) { btn.setAttribute("aria-pressed", dark ? "true" : "false"); });
    doc.querySelectorAll("[data-mode-set]").forEach(function (btn) { btn.setAttribute("aria-pressed", btn.dataset.modeSet === mode ? "true" : "false"); });
    doc.querySelectorAll("[data-palette-set]").forEach(function (btn) { btn.setAttribute("aria-checked", btn.dataset.paletteSet === pal ? "true" : "false"); });
    var bg = cssVar("--bg", dark ? "#0b1a1d" : "#eef3f4");
    doc.querySelectorAll('meta[name="theme-color"]').forEach(function (m) { m.setAttribute("content", bg); });
  }
  // Run a visual change inside a circular reveal that starts at the click (falls back to instant).
  function withReveal(update, evt) {
    if (!doc.startViewTransition || reduceMotion) { update(); return; }
    var x = evt && evt.clientX ? evt.clientX : window.innerWidth / 2;
    var y = evt && evt.clientY ? evt.clientY : 0;
    root.classList.add("vt-theme");
    var t;
    try { t = doc.startViewTransition(update); } catch (e) { root.classList.remove("vt-theme"); update(); return; }
    var radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    t.ready.then(function () {
      root.animate({ clipPath: ["circle(0px at " + x + "px " + y + "px)", "circle(" + radius + "px at " + x + "px " + y + "px)"] },
        { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" });
    }).catch(function () { /* transition skipped */ });
    t.finished.then(function () { root.classList.remove("vt-theme"); }, function () { root.classList.remove("vt-theme"); });
  }
  function setMode(mode, evt) {
    withReveal(function () {
      try { if (mode === "auto") localStorage.removeItem("theme"); else localStorage.setItem("theme", mode); } catch (e) { /* private mode */ }
      root.classList.toggle("dark", mode === "dark" || (mode === "auto" && systemDark()));
      syncAppearanceUi();
    }, evt);
  }
  function setPalette(key, evt) {
    withReveal(function () {
      root.dataset.palette = key;
      try { localStorage.setItem("palette", key); } catch (e) { /* private mode */ }
      setCookie("palette", key);
      syncAppearanceUi();
    }, evt);
  }
  function toggleTheme(evt) { setMode(root.classList.contains("dark") ? "light" : "dark", evt && evt.clientX !== undefined ? evt : null); }
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onSystem = function () { if (getMode() === "auto") { root.classList.toggle("dark", mq.matches); syncAppearanceUi(); } };
    if (mq.addEventListener) mq.addEventListener("change", onSystem);
  }
  // keep the server-visible cookie in step with the locally saved palette
  try { var savedPalette = localStorage.getItem("palette"); if (savedPalette) setCookie("palette", savedPalette); } catch (e) { /* ignore */ }

  var apPop = doc.getElementById("appearance-pop"), apBack = doc.getElementById("appearance-backdrop"), apTrigger = null;
  function openAppearance(trigger) {
    if (!apPop) return;
    closeDrawer(false);
    apTrigger = trigger || null;
    apPop.hidden = false; apBack.hidden = false;
    if (trigger && trigger.setAttribute) trigger.setAttribute("aria-expanded", "true");
    var first = apPop.querySelector('[aria-checked="true"]') || apPop.querySelector("button, a");
    if (first) first.focus();
  }
  function closeAppearance() {
    if (!apPop || apPop.hidden) return;
    apPop.hidden = true; apBack.hidden = true;
    doc.querySelectorAll("[data-appearance-open]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    if (apTrigger && apTrigger.focus) apTrigger.focus();
  }
  doc.addEventListener("click", function (evt) {
    var t = evt.target;
    var open = t.closest("[data-appearance-open]");
    if (open) { openAppearance(open); return; }
    if (t.closest("[data-appearance-close]")) { closeAppearance(); return; }
    var mode = t.closest("[data-mode-set]");
    if (mode) { setMode(mode.dataset.modeSet, evt); return; }
    var pal = t.closest("[data-palette-set]");
    if (pal) { setPalette(pal.dataset.paletteSet, evt); return; }
    if (t.closest("[data-theme-toggle]")) toggleTheme(evt);
  });
  doc.addEventListener("keydown", function (evt) {
    if (evt.key === "Escape") closeAppearance();
    if (evt.key === "Tab" && apPop && !apPop.hidden) {
      var f = apPop.querySelectorAll("button, a[href]");
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (evt.shiftKey && doc.activeElement === first) { evt.preventDefault(); last.focus(); }
      else if (!evt.shiftKey && doc.activeElement === last) { evt.preventDefault(); first.focus(); }
    }
  });
  syncAppearanceUi();

  /* ---------- "Install app" (only when the browser offers it) ---------- */
  var installEvent = null;
  window.addEventListener("beforeinstallprompt", function (evt) {
    evt.preventDefault(); installEvent = evt;
    doc.querySelectorAll("[data-install]").forEach(function (b) { b.hidden = false; });
  });
  window.addEventListener("appinstalled", function () {
    installEvent = null;
    doc.querySelectorAll("[data-install]").forEach(function (b) { b.hidden = true; });
  });
  doc.addEventListener("click", function (evt) {
    if (!evt.target.closest("[data-install]") || !installEvent) return;
    installEvent.prompt();
    installEvent.userChoice.then(function () {
      installEvent = null;
      doc.querySelectorAll("[data-install]").forEach(function (b) { b.hidden = true; });
    });
  });

  /* ---------- Hamburger drawer (all sections live here) ---------- */
  var drawer = doc.getElementById("drawer");
  var backdrop = doc.getElementById("drawer-backdrop");
  var burger = doc.querySelector(".burger");
  var drawerTrigger = null;
  function drawerOpen() { return drawer && !drawer.hidden && drawer.classList.contains("is-open"); }
  function openDrawer(trigger) {
    if (!drawer) return;
    drawerTrigger = trigger || burger;
    drawer.hidden = false; backdrop.hidden = false;
    requestAnimationFrame(function () {
      drawer.classList.add("is-open"); backdrop.classList.add("is-open");
      if (burger) { burger.setAttribute("aria-expanded", "true"); burger.classList.add("is-open"); }
    });
    doc.body.classList.add("no-scroll");
    var current = drawer.querySelector('[aria-current="page"]') || drawer.querySelector("a, button");
    if (current) setTimeout(function () { current.focus({ preventScroll: true }); }, 60);
  }
  function closeDrawer(returnFocus) {
    if (!drawer || drawer.hidden) return;
    drawer.classList.remove("is-open"); backdrop.classList.remove("is-open");
    if (burger) { burger.setAttribute("aria-expanded", "false"); burger.classList.remove("is-open"); }
    doc.body.classList.remove("no-scroll");
    setTimeout(function () { drawer.hidden = true; backdrop.hidden = true; }, reduceMotion ? 0 : 380);
    if (returnFocus !== false && drawerTrigger) drawerTrigger.focus();
  }
  doc.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-drawer-open]")) { drawerOpen() ? closeDrawer() : openDrawer(evt.target.closest("[data-drawer-open]")); return; }
    if (evt.target.closest("[data-drawer-close]")) { closeDrawer(); return; }
    if (drawerOpen() && evt.target.closest("#drawer a")) closeDrawer(false);
  });
  doc.addEventListener("keydown", function (evt) {
    if (evt.key === "Escape" && drawerOpen()) { closeDrawer(); return; }
    if (evt.key === "Tab" && drawerOpen()) {            // keep keyboard focus inside the open drawer
      var items = drawer.querySelectorAll("a[href], button:not([disabled])");
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (evt.shiftKey && doc.activeElement === first) { evt.preventDefault(); last.focus(); }
      else if (!evt.shiftKey && doc.activeElement === last) { evt.preventDefault(); first.focus(); }
    }
  });

  /* ---------- Command palette (Ctrl/⌘+K or "/") ---------- */
  var palette = null, paletteItems = [], paletteIdx = 0, paletteReturn = null;
  function collectCommands() {
    var cmds = [];
    doc.querySelectorAll("#drawer a[data-cmd]").forEach(function (a) {
      var label = a.querySelector("b"), hint = a.querySelector("small"), icon = a.querySelector("use");
      cmds.push({ label: label ? label.textContent : a.textContent.trim(), hint: hint ? hint.textContent : "", href: a.getAttribute("href"), icon: icon ? icon.getAttribute("href") : "#i-search" });
    });
    cmds.push({ label: T("تغییر پوسته‌ی روشن/تاریک"), hint: T("میان‌بر"), icon: "#i-moon", run: toggleTheme });
    var popRoot = doc.getElementById("appearance-pop");
    if (popRoot) {
      popRoot.querySelectorAll("[data-palette-set]").forEach(function (b) {
        var nm = b.querySelector(".sw-name");
        cmds.push({ label: nm ? nm.textContent : b.dataset.paletteSet, hint: T("رنگ‌بندی"), icon: "#i-palette", run: function () { setPalette(b.dataset.paletteSet, null); } });
      });
      popRoot.querySelectorAll("a[hreflang]:not([aria-current])").forEach(function (a) {
        cmds.push({ label: a.textContent.trim(), hint: T("زبان"), icon: "#i-globe", href: a.getAttribute("href") });
      });
    }
    return cmds;
  }
  function buildPalette() {
    palette = doc.createElement("div");
    palette.className = "palette"; palette.hidden = true;
    palette.innerHTML = '<div class="palette-backdrop" data-palette-close></div>' +
      '<div class="palette-box" role="dialog" aria-modal="true" aria-label="' + T("جستجوی سریع") + '">' +
      '<input class="palette-input" type="search" placeholder="' + T("برو به… (مثلاً آمار، عادت‌ها)") + '" aria-label="' + T("جستجوی سریع") + '" autocomplete="off">' +
      '<ul class="palette-list" role="listbox"></ul>' +
      '<div class="palette-foot"><span>' + T("↑↓ انتخاب") + '</span><span>' + T("Enter باز کردن") + '</span><span>' + T("Esc بستن") + '</span></div></div>';
    doc.body.appendChild(palette);
    palette.addEventListener("click", function (e) {
      if (e.target.closest("[data-palette-close]")) closePalette();
      var li = e.target.closest("li[data-i]"); if (li) runPalette(parseInt(li.dataset.i, 10));
    });
    palette.querySelector(".palette-input").addEventListener("input", renderPalette);
    palette.querySelector(".palette-input").addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); paletteIdx = Math.min(paletteItems.length - 1, paletteIdx + 1); markPalette(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); paletteIdx = Math.max(0, paletteIdx - 1); markPalette(); }
      else if (e.key === "Enter") { e.preventDefault(); runPalette(paletteIdx); }
      else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
    });
  }
  function renderPalette() {
    var q = palette.querySelector(".palette-input").value.trim().toLowerCase();
    var all = collectCommands();
    paletteItems = q ? all.filter(function (c) { return (c.label + " " + c.hint).toLowerCase().indexOf(q) !== -1; }) : all;
    paletteIdx = 0;
    var list = palette.querySelector(".palette-list");
    list.innerHTML = "";
    if (!paletteItems.length) {
      var none = doc.createElement("li"); none.className = "palette-none"; none.textContent = T("چیزی پیدا نشد."); list.appendChild(none); return;
    }
    paletteItems.forEach(function (c, i) {
      var li = doc.createElement("li"); li.dataset.i = i; li.setAttribute("role", "option");
      li.innerHTML = '<svg class="i" aria-hidden="true"><use href="' + c.icon + '"/></svg><span><b></b><small></small></span>';
      li.querySelector("b").textContent = c.label; li.querySelector("small").textContent = c.hint;
      list.appendChild(li);
    });
    markPalette();
  }
  function markPalette() {
    palette.querySelectorAll("li[data-i]").forEach(function (li, i) {
      var on = i === paletteIdx; li.classList.toggle("is-active", on); li.setAttribute("aria-selected", on ? "true" : "false");
      if (on) li.scrollIntoView({ block: "nearest" });
    });
  }
  function runPalette(i) {
    var c = paletteItems[i]; if (!c) return;
    closePalette();
    if (c.run) c.run(); else if (c.href) window.location.href = c.href;
  }
  function openPalette() {
    if (!doc.querySelector("#drawer")) return;       // only for signed-in pages
    if (!palette) buildPalette();
    closeDrawer(false);
    paletteReturn = doc.activeElement;
    palette.hidden = false; palette.querySelector(".palette-input").value = ""; renderPalette();
    requestAnimationFrame(function () { palette.classList.add("is-open"); palette.querySelector(".palette-input").focus(); });
  }
  function closePalette() {
    if (!palette || palette.hidden) return;
    palette.classList.remove("is-open");
    setTimeout(function () { palette.hidden = true; }, reduceMotion ? 0 : 180);
    if (paletteReturn && paletteReturn.focus) paletteReturn.focus();
  }
  doc.addEventListener("click", function (e) { if (e.target.closest("[data-palette-open]")) openPalette(); });
  doc.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    var typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); palette && !palette.hidden ? closePalette() : openPalette(); }
    else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); openPalette(); }
  });

  /* ---------- Toasts ---------- */
  function toast(message, kind) {
    var box = doc.getElementById("toast-container");
    if (!box || !message) return;
    message = T(message);
    var el = doc.createElement("div");
    el.className = "toast" + (kind === "error" ? " is-error" : "");
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () {
      el.classList.add("is-leaving");
      setTimeout(function () { el.remove(); }, 220);
    }, 2800);
  }
  window.growthToast = toast;
  doc.body.addEventListener("toast", function (evt) {
    toast(evt.detail && (evt.detail.value || evt.detail));
  });

  /* ---------- Confetti (only when the last open task of today is done) ---------- */
  function confetti() {
    if (reduceMotion) return;
    var layer = doc.createElement("div");
    layer.className = "confetti";
    layer.setAttribute("aria-hidden", "true");
    var colors = [cssVar("--primary", "#0b7a84"), cssVar("--accent", "#e9a612"), cssVar("--primary-text", "#4cc3cc"), cssVar("--accent-text", "#f2b93b"), cssVar("--ok", "#1b7547"), cssVar("--danger", "#b5322a")];
    for (var i = 0; i < 46; i++) {
      var p = doc.createElement("i");
      p.style.left = Math.random() * 100 + "%";
      p.style.background = colors[i % colors.length];
      p.style.setProperty("--x", (Math.random() * 160 - 80) + "px");
      p.style.setProperty("--r", (Math.random() * 720 - 360) + "deg");
      p.style.setProperty("--d", (1.5 + Math.random() * 1.2) + "s");
      p.style.setProperty("--delay", (Math.random() * 0.35) + "s");
      layer.appendChild(p);
    }
    doc.body.appendChild(layer);
    setTimeout(function () { layer.remove(); }, 3400);
  }

  window.growthConfetti = confetti;

  /* ---------- Today ring: derived from the rows actually on the page ---------- */
  function updateRing() {
    var ring = doc.querySelector("[data-ring]");
    var list = doc.getElementById("task-list");
    if (!ring || !list) return;
    var tasks = list.querySelectorAll(".task");
    var total = tasks.length;
    var done = list.querySelectorAll('.task[data-status="done"]').length;
    var pct = total ? Math.round(done * 100 / total) : 0;
    ring.style.setProperty("--p", pct);
    ring.classList.toggle("is-complete", total > 0 && done === total);
    var pctEl = ring.querySelector("[data-ring-pct]");
    var cntEl = ring.querySelector("[data-ring-count]");
    if (pctEl) pctEl.textContent = faDigits(pct) + (LANG === "en" ? "%" : "٪");
    if (cntEl) cntEl.textContent = faDigits(done) + " " + T("از") + " " + faDigits(total);
    var msg = doc.querySelector("[data-hero-msg]");
    if (msg) {
      var left = total - done;
      msg.textContent = total === 0 ? msg.dataset.msgEmpty
        : left === 0 ? msg.dataset.msgDone
        : msg.dataset.msgProgress.replace("{n}", faDigits(left));
    }
    var complete = total > 0 && done === total;
    if (complete && ring.dataset.complete !== "1") { confetti(); haptic([12, 40, 18]); }
    ring.dataset.complete = complete ? "1" : "0";
  }

  /* ---------- HTMX integration ---------- */
  var quiet = false;
  doc.body.addEventListener("htmx:load", function (evt) {
    var el = evt.target;
    if (quiet) return;  // background refreshes shouldn't replay entrance animations
    if (el && el.classList && el.classList.contains("task")) el.classList.add("is-new");
  });

  // A 422 from the quick-add form means "validation errors": show them in the form.
  doc.body.addEventListener("htmx:beforeSwap", function (evt) {
    if (evt.detail.xhr.status === 422) {
      var form = doc.getElementById("task-form");
      if (form) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
        evt.detail.target = form;
        evt.detail.swapOverride = "outerHTML";
      }
    }
  });

  doc.body.addEventListener("htmx:responseError", function (evt) {
    if (evt.detail.xhr.status === 422) return;
    toast(T("یه مشکلی پیش اومد؛ دوباره امتحان کن."), "error");
  });
  doc.body.addEventListener("htmx:sendError", function () {
    toast(T("اتصال اینترنت قطع است. دوباره امتحان کن."), "error");
  });

  function refreshLists(except) {
    // Rows in the review panel and rows in today's list are copies of the same tasks;
    // after a change in one place, re-fetch the other so they never disagree.
    var panel = doc.getElementById("review-panel");
    var reviewBtn = doc.querySelector("[data-review-url]");
    quiet = true; setTimeout(function () { quiet = false; }, 600);
    if (except !== "list" && doc.getElementById("task-list")) {
      htmx.ajax("GET", location.pathname + location.search, { target: "#task-list", select: "#task-list", swap: "outerHTML" });
    }
    if (except !== "review" && panel && panel.children.length && reviewBtn) {
      htmx.ajax("GET", reviewBtn.dataset.reviewUrl, { target: "#review-panel", swap: "outerHTML" });
    }
  }
  doc.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-refresh-lists]")) refreshLists();
  });

  function refreshOtherViews(evt) {
    var cfg = evt.detail.requestConfig || {};
    if (!evt.detail.successful || (cfg.verb || "").toLowerCase() !== "post") return;
    var elt = evt.detail.elt;
    var inReview = elt && elt.closest && elt.closest("#review-panel");
    refreshLists(inReview ? "review" : "list");
  }

  doc.body.addEventListener("htmx:afterRequest", function (evt) {
    var elt = evt.detail.elt;
    if (evt.detail.successful && elt && elt.classList && elt.classList.contains("check")) haptic(12);
    if (evt.detail.successful && elt && elt.dataset && elt.dataset.toast) toast(elt.dataset.toast);
    refreshOtherViews(evt);
  });
  doc.body.addEventListener("htmx:afterSettle", function () {
    // Deleted rows are removed after their exit transition; recount once things settle.
    setTimeout(updateRing, 30);
  });
  updateRing();

  /* ---------- Press feedback for primary buttons on touch devices ---------- */
  doc.addEventListener("pointerdown", function (evt) {
    if (evt.pointerType === "touch" && evt.target.closest(".btn-primary, .btn-accent")) haptic(6);
  }, { passive: true });

  /* ---------- Shortcut: "n" focuses the quick-add field ---------- */
  doc.addEventListener("keydown", function (evt) {
    if (evt.key !== "n" && evt.key !== "N") return;
    if (evt.ctrlKey || evt.metaKey || evt.altKey) return;
    var tag = (evt.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || evt.target.isContentEditable) return;
    var field = doc.getElementById("id_title");
    if (field) {
      evt.preventDefault();
      field.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
      field.focus();
    }
  });

  /* ---------- Timeline: start the view at the current time (or the first task) ---------- */
  var tl = doc.querySelector("[data-timeline]");
  if (tl) {
    var target = tl.querySelector(".tl-now") || tl.querySelector(".tl-event");
    if (target) {
      var y = target.getBoundingClientRect().top + window.scrollY - 180;
      window.scrollTo({ top: Math.max(0, y), behavior: "auto" });
    }
  }

  /* ---------- Spotlight: cards glow where the pointer is (desktop only) ---------- */
  if (window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches && !reduceMotion) {
    doc.addEventListener("pointermove", function (e) {
      var card = e.target.closest && e.target.closest(".spot");
      if (!card) return;
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", (e.clientX - r.left) + "px");
      card.style.setProperty("--my", (e.clientY - r.top) + "px");
    }, { passive: true });
  }

  /* ---------- Reveal-on-scroll for landing sections ---------- */
  var reveals = doc.querySelectorAll("[data-reveal]");
  if (reveals.length) {
    if (!("IntersectionObserver" in window) || reduceMotion) {
      reveals.forEach(function (el) { el.classList.add("is-in"); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); } });
      }, { threshold: 0.15, rootMargin: "0px 0px -6% 0px" });
      reveals.forEach(function (el) { io.observe(el); });
    }
  }

  /* ---------- Rescheduling: date-picker button on every open task + week-board drag & drop ---------- */
  function csrfToken() {
    try { return JSON.parse(doc.body.getAttribute("hx-headers"))["X-CSRFToken"]; } catch (e) { return ""; }
  }
  function listFor(date) {
    return doc.querySelector('[data-task-list][data-date="' + date + '"]');
  }
  function updateWeek() {
    var board = doc.querySelector("[data-week]");
    if (!board) return;
    var allTotal = 0, allDone = 0;
    board.querySelectorAll(".wday").forEach(function (col) {
      var total = col.querySelectorAll(".task").length;
      var done = col.querySelectorAll('.task[data-status="done"]').length;
      allTotal += total; allDone += done;
      var chip = col.querySelector("[data-wcount]");
      if (chip) chip.textContent = faDigits(done) + "/" + faDigits(total);
      var bar = col.querySelector(".progress > span");
      if (bar) bar.style.setProperty("--w", (total ? Math.round(done * 100 / total) : 0) + "%");
    });
    var sum = doc.querySelector("[data-week-summary]");
    if (sum) sum.textContent = tf("{d} از {d} تسک انجام شده", [faDigits(allDone), faDigits(allTotal)]);
  }
  function reschedule(row, url, date) {
    var parent = row.closest("[data-task-list]");
    if (parent && parent.dataset.date === date) return Promise.resolve(false);
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ date: date }).toString()
    }).then(function (res) {
      return res.text().then(function (text) {
        if (!res.ok) { toast(T(text) || T("جابه‌جایی انجام نشد."), "error"); return false; }
        var target = listFor(date);
        row.classList.add("htmx-swapping");
        setTimeout(function () {
          row.remove();
          if (target) {
            var tpl = doc.createElement("template");
            tpl.innerHTML = text.trim();
            var fresh = tpl.content.firstElementChild;
            if (fresh) { target.appendChild(fresh); if (window.htmx) htmx.process(fresh); }
          }
          armDraggables(); updateRing(); updateWeek();
          toast(T(target ? "جابه‌جا شد" : "به روز دیگری منتقل شد"));
        }, reduceMotion ? 0 : 200);
        return true;
      });
    }).catch(function () { toast(T("اتصال اینترنت قطع است."), "error"); return false; });
  }

  var pickerInput = null, pickerRow = null, pickerUrl = null;
  doc.addEventListener("click", function (evt) {
    var btn = evt.target.closest("[data-resched]");
    if (!btn) return;
    pickerRow = btn.closest(".task"); pickerUrl = btn.dataset.url;
    if (!pickerInput) {
      pickerInput = doc.createElement("input");
      pickerInput.type = "date"; pickerInput.className = "sr-only"; pickerInput.tabIndex = -1;
      pickerInput.setAttribute("aria-label", T("روز جدید"));
      pickerInput.addEventListener("change", function () {
        if (pickerInput.value && pickerRow) reschedule(pickerRow, pickerUrl, pickerInput.value);
      });
      doc.body.appendChild(pickerInput);
    }
    var list = pickerRow && pickerRow.closest("[data-task-list]");
    pickerInput.value = list && list.dataset.date ? list.dataset.date : "";
    var r = btn.getBoundingClientRect();
    pickerInput.style.cssText = "position:fixed;left:" + Math.round(r.left) + "px;top:" + Math.round(r.bottom) + "px;width:1px;height:1px;opacity:0";
    if (pickerInput.showPicker) { try { pickerInput.showPicker(); return; } catch (e) { /* fall through */ } }
    pickerInput.focus(); pickerInput.click();
  });

  // Week board: drag a task card onto another day.
  var dragged = null;
  function armDraggables(scope) {
    (scope || doc).querySelectorAll("[data-week] .task[data-open]:not([data-habit])").forEach(function (t) { t.draggable = true; });
  }
  doc.addEventListener("dragstart", function (evt) {
    var row = evt.target.closest && evt.target.closest(".task[draggable='true']");
    if (!row) return;
    dragged = row; row.classList.add("is-dragging");
    evt.dataTransfer.effectAllowed = "move";
    evt.dataTransfer.setData("text/plain", row.dataset.id || "");
  });
  doc.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("is-dragging");
    dragged = null;
    doc.querySelectorAll(".wday.drop-hover").forEach(function (c) { c.classList.remove("drop-hover"); });
  });
  doc.addEventListener("dragover", function (evt) {
    var col = dragged && evt.target.closest && evt.target.closest(".wday");
    if (!col) return;
    evt.preventDefault();
    doc.querySelectorAll(".wday.drop-hover").forEach(function (c) { if (c !== col) c.classList.remove("drop-hover"); });
    col.classList.add("drop-hover");
  });
  doc.addEventListener("drop", function (evt) {
    var col = dragged && evt.target.closest && evt.target.closest(".wday");
    if (!col) return;
    evt.preventDefault();
    var list = col.querySelector("[data-task-list]");
    var btn = dragged.querySelector("[data-resched]");
    col.classList.remove("drop-hover");
    if (list && btn) reschedule(dragged, btn.dataset.url, list.dataset.date);
  });
  armDraggables();
  doc.body.addEventListener("htmx:afterSettle", function () { armDraggables(); updateWeek(); });
  // Bring today's column to the middle of the board; scroll only the board, never the page.
  var weekBoard = doc.querySelector("[data-week]");
  var todayCol = weekBoard && weekBoard.querySelector(".wday.is-today");
  if (todayCol) {
    var bRect = weekBoard.getBoundingClientRect(), cRect = todayCol.getBoundingClientRect();
    weekBoard.scrollBy({ left: (cRect.left + cRect.width / 2) - (bRect.left + bRect.width / 2), behavior: "auto" });
  }

  /* ---------- Staggered entrance for lists marked data-stagger (page load only) ---------- */
  doc.querySelectorAll("[data-stagger]").forEach(function (list) {
    Array.prototype.slice.call(list.children, 0, 14).forEach(function (child, i) {
      child.classList.add("reveal");
      child.style.setProperty("--delay", (i * 0.05) + "s");
    });
  });

  /* ---------- Count-up numbers (stats), start when visible ---------- */
  function countUp(el) {
    var target = parseInt(el.dataset.countup, 10);
    if (isNaN(target)) return;
    if (reduceMotion || target === 0) { el.textContent = faDigits(target); return; }
    var start = null, dur = 900;
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / dur);
      el.textContent = faDigits(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counters = doc.querySelectorAll("[data-countup]");
  if (counters.length) {
    if ("IntersectionObserver" in window) {
      var cio = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { countUp(en.target); cio.unobserve(en.target); } });
      }, { threshold: 0.4 });
      counters.forEach(function (el) { cio.observe(el); });
    } else { counters.forEach(countUp); }
  }

  /* ---------- Thin loading bar for any HTMX request + button ripple ---------- */
  var bar = doc.createElement("div");
  bar.className = "topbar"; bar.setAttribute("aria-hidden", "true");
  doc.body.appendChild(bar);
  var inflight = 0;
  doc.body.addEventListener("htmx:beforeRequest", function () { inflight++; bar.classList.add("is-on"); });
  function endRequest() { inflight = Math.max(0, inflight - 1); if (!inflight) bar.classList.remove("is-on"); }
  doc.body.addEventListener("htmx:afterRequest", endRequest);

  doc.addEventListener("pointerdown", function (evt) {
    var btn = evt.target.closest(".btn");
    if (!btn || reduceMotion || btn.classList.contains("htmx-request")) return;
    var rect = btn.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height) * 1.6;
    var dot = doc.createElement("span");
    dot.className = "ripple";
    dot.style.width = dot.style.height = size + "px";
    dot.style.left = (evt.clientX - rect.left - size / 2) + "px";
    dot.style.top = (evt.clientY - rect.top - size / 2) + "px";
    btn.appendChild(dot);
    setTimeout(function () { dot.remove(); }, 650);
  }, { passive: true });

  /* ---------- Card tilt + cursor spotlight (fine pointers only, never with reduced motion) ---------- */
  var finePointer = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (finePointer && !reduceMotion) {
    doc.addEventListener("pointermove", function (evt) {
      var el = evt.target.closest && evt.target.closest(".tilt, .glow");
      if (!el) return;
      var r = el.getBoundingClientRect();
      var x = (evt.clientX - r.left) / r.width, y = (evt.clientY - r.top) / r.height;
      el.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
      el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
      if (el.classList.contains("tilt")) {
        el.style.setProperty("--ry", ((x - 0.5) * 8).toFixed(2) + "deg");
        el.style.setProperty("--rx", ((0.5 - y) * 8).toFixed(2) + "deg");
      }
    }, { passive: true });
    doc.addEventListener("pointerout", function (evt) {
      var el = evt.target.closest && evt.target.closest(".tilt");
      if (el && !el.contains(evt.relatedTarget)) { el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); }
    }, { passive: true });
  }

  /* ---------- Celebration when a goal has just been completed ---------- */
  if (doc.querySelector("[data-celebrate]")) {
    setTimeout(function () { confetti(); haptic([12, 40, 18]); }, 350);
  }

  /* ---------- Keyboard: "g" then a letter jumps to a section, "?" lists every shortcut ---------- */
  var chordKeys = {};
  doc.querySelectorAll("[data-cmd][data-key]").forEach(function (a) {
    var label = a.querySelector("b");
    chordKeys[a.dataset.key] = { href: a.getAttribute("href"), label: label ? label.textContent : a.textContent.trim() };
  });
  var chordArmed = false, chordTimer = null, helpEl = null;
  function disarm() { chordArmed = false; clearTimeout(chordTimer); var hint = doc.querySelector(".chord-hint"); if (hint) hint.remove(); }
  function arm() {
    chordArmed = true;
    var hint = doc.createElement("div");
    hint.className = "chord-hint"; hint.setAttribute("aria-hidden", "true");
    hint.innerHTML = "<kbd>g</kbd> " + T("سپس یک حرف…");
    doc.body.appendChild(hint);
    chordTimer = setTimeout(disarm, 1600);
  }
  function closeHelp() { if (helpEl) { helpEl.remove(); helpEl = null; } }
  function openHelp() {
    if (helpEl) return closeHelp();
    helpEl = doc.createElement("div");
    helpEl.className = "help-pop"; helpEl.setAttribute("role", "dialog"); helpEl.setAttribute("aria-modal", "true"); helpEl.setAttribute("aria-label", T("میانبرهای صفحه‌کلید"));
    var rows = '<div class="help-row"><span>' + T("تسک جدید") + '</span><span><kbd>n</kbd></span></div>' +
               '<div class="help-row"><span>' + T("جستجو و پرش سریع") + '</span><span><kbd>Ctrl</kbd> <kbd>K</kbd></span></div>' +
               '<div class="help-row"><span>' + T("این راهنما") + '</span><span><kbd>?</kbd></span></div>';
    Object.keys(chordKeys).forEach(function (k) {
      rows += '<div class="help-row"><span>' + chordKeys[k].label + '</span><span><kbd>g</kbd> <kbd>' + k + '</kbd></span></div>';
    });
    helpEl.innerHTML = '<div class="help-backdrop" data-help-close></div><div class="help-card"><div class="row between mb-3"><h2 class="card-title">' + T("میانبرهای صفحه‌کلید") + '</h2>' +
      '<button type="button" class="icon-btn" data-help-close aria-label="' + T("بستن") + '"><svg class="i" aria-hidden="true"><use href="#i-x"/></svg></button></div>' + rows + '</div>';
    doc.body.appendChild(helpEl);
    var closeBtn = helpEl.querySelector("button"); if (closeBtn) closeBtn.focus();
  }
  doc.addEventListener("click", function (evt) { if (evt.target.closest("[data-help-close]")) closeHelp(); });
  doc.addEventListener("keydown", function (evt) {
    if (evt.key === "Escape") { closeHelp(); disarm(); return; }
    if (evt.ctrlKey || evt.metaKey || evt.altKey) return;
    var tag = (evt.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || evt.target.isContentEditable) return;
    if (chordArmed) {
      var hit = chordKeys[evt.key.toLowerCase()];
      disarm();
      if (hit) { evt.preventDefault(); window.location.href = hit.href; }
      return;
    }
    if (evt.key === "?") { evt.preventDefault(); openHelp(); }
    else if ((evt.key === "g" || evt.key === "G") && Object.keys(chordKeys).length) { evt.preventDefault(); arm(); }
  });

  /* ---------- Welcome tour (spotlight steps; shown once, restartable from the menu) ---------- */
  var tourTpl = doc.getElementById("tour-data");
  var tour = null;
  function tourVisible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  }
  function endTour(markSeen) {
    if (!tour) return;
    tour.el.remove(); tour = null;
    window.removeEventListener("resize", placeTour); window.removeEventListener("scroll", placeTour, true);
    if (markSeen) { try { localStorage.setItem("tour-v1", "1"); } catch (e) { /* ignore */ } }
  }
  function placeTour() {
    if (!tour) return;
    var step = tour.steps[tour.i], card = tour.card, spot = tour.spot;
    var target = step.sel ? doc.querySelector(step.sel) : null;
    var vw = window.innerWidth, vh = window.innerHeight;
    if (target && tourVisible(target)) {
      var r = target.getBoundingClientRect(), pad = 6;
      spot.hidden = false;
      spot.style.cssText = "top:" + (r.top - pad) + "px;left:" + (r.left - pad) + "px;width:" + (r.width + pad * 2) + "px;height:" + (r.height + pad * 2) + "px";
      var cw = Math.min(320, vw - 24);
      card.style.width = cw + "px";
      var below = r.bottom + 14 + card.offsetHeight < vh || r.top < card.offsetHeight + 24;
      var top = below ? r.bottom + 14 : r.top - card.offsetHeight - 14;
      var left = Math.max(12, Math.min(vw - cw - 12, r.left + r.width / 2 - cw / 2));
      card.style.top = Math.max(12, Math.min(vh - card.offsetHeight - 12, top)) + "px";
      card.style.left = left + "px";
    } else {
      spot.hidden = true;
      var w = Math.min(340, vw - 24);
      card.style.width = w + "px";
      card.style.top = Math.max(12, (vh - card.offsetHeight) / 2) + "px";
      card.style.left = Math.max(12, (vw - w) / 2) + "px";
    }
  }
  function showTourStep() {
    var step = tour.steps[tour.i], n = tour.steps.length, last = tour.i === n - 1;
    var target = step.sel ? doc.querySelector(step.sel) : null;
    if (target && target.scrollIntoView && tourVisible(target)) target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
    tour.card.innerHTML = '<p class="tour-step">' + tf("قدم {d} از {d}", [faDigits(tour.i + 1), faDigits(n)]) + '</p>' +
      '<h2 class="tour-title"></h2><p class="tour-text"></p>' +
      '<div class="tour-dots" aria-hidden="true">' + tour.steps.map(function (_, k) { return '<i' + (k === tour.i ? ' class="on"' : '') + '></i>'; }).join("") + '</div>' +
      '<div class="tour-actions"><button type="button" class="btn btn-ghost btn-sm" data-tour-skip>' + T("رد کردن") + '</button><span class="grow"></span>' +
      (tour.i > 0 ? '<button type="button" class="btn btn-ghost btn-sm" data-tour-prev>' + T("قبلی") + '</button>' : '') +
      '<button type="button" class="btn btn-primary btn-sm" data-tour-next>' + (last ? T("پایان") : T("بعدی")) + '</button></div>';
    tour.card.querySelector(".tour-title").textContent = step.title;
    tour.card.querySelector(".tour-text").textContent = step.text;
    tour.card.classList.remove("is-in"); void tour.card.offsetWidth; tour.card.classList.add("is-in");
    setTimeout(placeTour, reduceMotion ? 0 : 260);
    placeTour();
    var next = tour.card.querySelector("[data-tour-next]"); if (next) next.focus();
  }
  function startTour() {
    if (!tourTpl || tour) return;
    closeDrawer(false); closeAppearance();
    var steps = Array.prototype.map.call(tourTpl.content.querySelectorAll("li"), function (li) {
      return { sel: li.dataset.sel, title: li.dataset.title, text: li.dataset.text };
    }).filter(function (st) { return !st.sel || tourVisible(doc.querySelector(st.sel)); });
    if (!steps.length) return;
    var el = doc.createElement("div");
    el.className = "tour"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
    el.innerHTML = '<div class="tour-spot" hidden></div><div class="tour-card"></div>';
    doc.body.appendChild(el);
    tour = { el: el, spot: el.querySelector(".tour-spot"), card: el.querySelector(".tour-card"), steps: steps, i: 0 };
    window.addEventListener("resize", placeTour); window.addEventListener("scroll", placeTour, true);
    showTourStep();
  }
  doc.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-tour-start]")) { startTour(); return; }
    if (!tour) return;
    if (evt.target.closest("[data-tour-skip]")) endTour(true);
    else if (evt.target.closest("[data-tour-prev]")) { tour.i = Math.max(0, tour.i - 1); showTourStep(); }
    else if (evt.target.closest("[data-tour-next]")) {
      if (tour.i >= tour.steps.length - 1) endTour(true); else { tour.i++; showTourStep(); }
    }
  });
  doc.addEventListener("keydown", function (evt) {
    if (!tour) return;
    if (evt.key === "Escape") { evt.stopPropagation(); endTour(true); }
    else if (evt.key === "ArrowLeft" || evt.key === "ArrowRight") {
      var forward = (evt.key === "ArrowLeft") === (doc.dir === "rtl" || root.dir === "rtl");
      if (forward) { if (tour.i < tour.steps.length - 1) { tour.i++; showTourStep(); } } else if (tour.i > 0) { tour.i--; showTourStep(); }
    }
  }, true);
  if (tourTpl && tourTpl.dataset.autostart === "1") {
    var seen = false;
    try { seen = localStorage.getItem("tour-v1") === "1"; } catch (e) { /* ignore */ }
    if (!seen) setTimeout(startTour, 1100);
  }

  /* ---------- Landing: the preview app finishes its own tasks in a loop ---------- */
  var demo = doc.querySelector("[data-demo]");
  if (demo && !reduceMotion) {
    var dTasks = demo.querySelectorAll(".task"), dRing = demo.querySelector(".ring");
    var dPct = dRing && dRing.querySelector("strong"), dCnt = dRing && dRing.querySelector(".ring-label span");
    var dMsg = demo.querySelector(".hero-msg"), DEMO_TOTAL = 5, dStage = 0;
    var confettiShown = 0;
    function paintDemo(done, statuses) {
      var pct = Math.round(done * 100 / DEMO_TOTAL);
      dRing.style.setProperty("--p", pct);
      dRing.classList.toggle("is-complete", done === DEMO_TOTAL);
      if (dPct) dPct.textContent = faDigits(pct) + (LANG === "en" ? "%" : "٪");
      if (dCnt) dCnt.textContent = faDigits(done) + " " + T("از") + " " + faDigits(DEMO_TOTAL);
      if (dMsg) dMsg.textContent = done === DEMO_TOTAL ? demo.dataset.msgDone : demo.dataset.msgProgress.replace("{n}", faDigits(DEMO_TOTAL - done));
      dTasks.forEach(function (t, i) { if (statuses[i]) t.dataset.status = statuses[i]; });
    }
    var frames = [
      { done: 3, s: ["done", "in_progress", "todo"] },
      { done: 4, s: ["done", "done", "in_progress"] },
      { done: 5, s: ["done", "done", "done"] }
    ];
    var frame = 0;
    setInterval(function () {
      if (doc.hidden) return;
      frame = (frame + 1) % (frames.length + 1);
      if (frame === frames.length) { paintDemo(3, ["done", "in_progress", "todo"]); frame = 0; return; }
      paintDemo(frames[frame].done, frames[frame].s);
      if (frames[frame].done === DEMO_TOTAL && confettiShown++ < 3) confetti();
    }, 2200);
  }

  /* ---------- Service worker (offline page + static caching) ---------- */
  var swUrl = doc.body.dataset.sw;
  if (swUrl && "serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register(swUrl).catch(function () { /* offline support is optional */ });
    });
  }
})();
