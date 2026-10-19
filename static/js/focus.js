/* Focus (pomodoro) timer. Uses timestamps, not tick counting, so it stays accurate
   when the tab is throttled or the phone sleeps. */
(function () {
  "use strict";
  var root = document.getElementById("focus");
  if (!root) return;

  var FA = "۰۱۲۳۴۵۶۷۸۹";
  var fa = function (v) { return (document.documentElement.lang || "fa").slice(0, 2) === "en" ? String(v) : String(v).replace(/\d/g, function (d) { return FA[d]; }); };
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var STORE = "focus:state";
  var DEFAULTS = { focus: 25, short: 5, long: 15 };
  var T = window.growthT || function (x) { return x; };
  var LABEL = { focus: T("در حال تمرکز…"), short: T("استراحت کن"), long: T("استراحت بلند") };
  var IDLE = { focus: T("آماده‌ای؟"), short: T("یک نفس عمیق"), long: T("یک نفس عمیق") };

  var ring = root.querySelector("[data-focus-ring]");
  var timeEl = root.querySelector("[data-focus-time]");
  var stateEl = root.querySelector("[data-focus-state]");
  var toggleBtn = root.querySelector("[data-focus-toggle]");
  var resetBtn = root.querySelector("[data-focus-reset]");
  var minutesEl = root.querySelector("[data-focus-minutes]");
  var taskSel = document.querySelector("[data-focus-task]");
  var doneBtn = document.querySelector("[data-focus-done]");
  var countEl = document.querySelector("[data-focus-count]");
  var dotsEl = document.querySelector("[data-focus-dots]");
  var baseTitle = document.title;

  var s = { mode: "focus", totalMs: 25 * 60000, remainingMs: 25 * 60000, endAt: null, minutes: { focus: 25, short: 5, long: 15 } };
  var timerId = null, wakeLock = null;

  function save() { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch (e) {} }
  function load() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORE) || "null");
      if (raw && raw.mode && raw.totalMs && raw.minutes) s = raw;
    } catch (e) {}
  }
  function todayKey() { var d = new Date(); return "focus:count:" + d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); }
  // Server-backed count (rendered into data-initial); localStorage is only a fallback if that is missing.
  var serverCount = parseInt((document.querySelector("[data-focus-count]") || { dataset: {} }).dataset.initial, 10);
  function getCount() {
    if (!isNaN(serverCount)) return serverCount;
    try { return parseInt(localStorage.getItem(todayKey()) || "0", 10) || 0; } catch (e) { return 0; }
  }
  function addCount() {
    if (!isNaN(serverCount)) { serverCount++; return; }
    try { localStorage.setItem(todayKey(), String(getCount() + 1)); } catch (e) {}
  }
  function logSession(minutes) {
    var token = document.querySelector("input[name=csrfmiddlewaretoken]");
    var url = root.dataset.logUrl;
    if (!url || !token) return;
    var body = new URLSearchParams({ minutes: String(minutes) });
    if (taskSel && taskSel.value) body.set("task", taskSel.value);
    fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": token.value, "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString()
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
      if (!data) { if (window.growthToast) window.growthToast(T("جلسه ثبت نشد؛ اتصالت را بررسی کن."), "error"); return; }
      serverCount = data.today_sessions; paintCount();
      var t = document.querySelector("[data-focus-today-min]"), w = document.querySelector("[data-focus-week-min]");
      var fmtMin = function (m) { var h = Math.floor(m / 60), r = m % 60; return window.growthTf ? window.growthTf(h && r ? "{d} ساعت و {d} دقیقه" : h ? "{d} ساعت" : "{d} دقیقه", h && r ? [fa(h), fa(r)] : h ? [fa(h)] : [fa(r)]) : fa(r); };
      if (t) t.textContent = fmtMin(data.today_minutes);
      if (w) w.textContent = fmtMin(data.week_minutes);
    }).catch(function () { if (window.growthToast) window.growthToast(T("جلسه ثبت نشد؛ اتصالت را بررسی کن."), "error"); });
  }

  function fmt(ms) {
    var total = Math.max(0, Math.ceil(ms / 1000));
    var m = Math.floor(total / 60), sec = total % 60;
    return fa((m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec);
  }
  function running() { return s.endAt !== null; }
  function left() { return running() ? Math.max(0, s.endAt - Date.now()) : s.remainingMs; }

  function paintCount() {
    var n = getCount();
    countEl.textContent = fa(n);
    dotsEl.innerHTML = "";
    for (var i = 0; i < Math.min(n, 12); i++) { var d = document.createElement("i"); d.style.setProperty("--i", i); dotsEl.appendChild(d); }
  }

  function paint() {
    var ms = left();
    timeEl.textContent = fmt(ms);
    ring.style.setProperty("--p", Math.round((1 - ms / s.totalMs) * 1000) / 10);
    root.dataset.mode = s.mode;
    root.classList.toggle("is-running", running());
    minutesEl.textContent = fa(s.minutes[s.mode]);
    root.querySelectorAll("[data-mode-btn]").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.modeBtn === s.mode ? "true" : "false"); });
    toggleBtn.querySelector("span").textContent = running() ? T("توقف") : (ms < s.totalMs ? T("ادامه") : T("شروع"));
    toggleBtn.querySelector("use").setAttribute("href", running() ? "#i-pause" : "#i-play");
    stateEl.textContent = running() ? LABEL[s.mode] : (ms < s.totalMs ? T("متوقف شده") : IDLE[s.mode]);
    document.title = running() ? timeEl.textContent + " · " + baseTitle : baseTitle;
    if (doneBtn) doneBtn.hidden = !(taskSel && taskSel.value);
  }

  async function lockScreen() {
    try { if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen"); } catch (e) {}
  }
  function unlockScreen() { try { if (wakeLock) wakeLock.release(); } catch (e) {} wakeLock = null; }

  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext; if (!Ctx) return;
      var ctx = new Ctx(), t = ctx.currentTime;
      [880, 1175].forEach(function (f, i) {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = f; o.type = "sine"; o.connect(g); g.connect(ctx.destination);
        g.gain.setValueAtTime(0.0001, t + i * 0.22); g.gain.exponentialRampToValueAtTime(0.25, t + i * 0.22 + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.22 + 0.4);
        o.start(t + i * 0.22); o.stop(t + i * 0.22 + 0.45);
      });
    } catch (e) {}
  }

  function tick() {
    if (left() <= 0) return finish();
    paint();
  }
  function start() {
    if (running()) return;
    if (s.remainingMs <= 0) s.remainingMs = s.totalMs;
    s.endAt = Date.now() + s.remainingMs;
    timerId = setInterval(tick, 250);
    lockScreen(); save(); paint();
  }
  function pause() {
    if (!running()) return;
    s.remainingMs = left(); s.endAt = null;
    clearInterval(timerId); timerId = null; unlockScreen(); save(); paint();
  }
  function setMode(mode) {
    pause();
    s.mode = mode; s.totalMs = s.minutes[mode] * 60000; s.remainingMs = s.totalMs; s.endAt = null;
    save(); paint();
  }
  function reset() { pause(); s.remainingMs = s.totalMs; save(); paint(); }

  function finish() {
    var wasFocus = s.mode === "focus";
    clearInterval(timerId); timerId = null; s.endAt = null; unlockScreen();
    s.remainingMs = 0; paint(); timeEl.textContent = fa("00:00");
    beep();
    try { if (navigator.vibrate) navigator.vibrate([200, 100, 200]); } catch (e) {}
    if (wasFocus) {
      logSession(s.minutes.focus);
      addCount(); paintCount();
      if (window.growthConfetti) window.growthConfetti();
      if (window.growthToast) window.growthToast(T("یک جلسه‌ی تمرکز تمام شد. آفرین!"));
      stateEl.textContent = T("جلسه تمام شد. وقت استراحت!");
      s.mode = "short";
    } else {
      if (window.growthToast) window.growthToast(T("استراحت تمام شد؛ برگردیم سر کار."));
      s.mode = "focus";
    }
    s.totalMs = s.minutes[s.mode] * 60000; s.remainingMs = s.totalMs; save();
    var msg = stateEl.textContent; paint(); if (wasFocus) stateEl.textContent = msg;
  }

  toggleBtn.addEventListener("click", function () { running() ? pause() : start(); });
  resetBtn.addEventListener("click", reset);
  root.querySelectorAll("[data-mode-btn]").forEach(function (b) { b.addEventListener("click", function () { setMode(b.dataset.modeBtn); }); });
  root.querySelectorAll("[data-adjust]").forEach(function (b) {
    b.addEventListener("click", function () {
      var next = Math.min(90, Math.max(5, s.minutes[s.mode] + parseInt(b.dataset.adjust, 10)));
      s.minutes[s.mode] = next;
      if (!running()) { s.totalMs = next * 60000; s.remainingMs = s.totalMs; }
      save(); paint();
    });
  });
  if (taskSel) taskSel.addEventListener("change", paint);

  if (doneBtn) {
    doneBtn.addEventListener("click", function () {
      var opt = taskSel.options[taskSel.selectedIndex];
      var url = opt && opt.dataset.doneUrl;
      var token = document.querySelector("input[name=csrfmiddlewaretoken]");
      if (!url || !token) return;
      doneBtn.setAttribute("aria-busy", "true");
      fetch(url, { method: "POST", headers: { "X-CSRFToken": token.value }, credentials: "same-origin" })
        .then(function (r) {
          if (!r.ok) throw new Error("bad status");
          opt.remove(); taskSel.value = ""; paint();
          if (window.growthConfetti) window.growthConfetti();
          if (window.growthToast) window.growthToast(T("تسک انجام‌شده ثبت شد."));
        })
        .catch(function () { if (window.growthToast) window.growthToast(T("ثبت نشد؛ دوباره امتحان کن."), "error"); })
        .finally(function () { doneBtn.removeAttribute("aria-busy"); });
    });
  }

  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.code === "Space" && tag !== "button" && tag !== "a") { e.preventDefault(); running() ? pause() : start(); }
    else if (e.key === "r" || e.key === "R") reset();
  });
  document.addEventListener("visibilitychange", function () { if (!document.hidden && running()) { tick(); lockScreen(); } });

  load();
  if (running()) { if (left() <= 0) { s.endAt = null; s.remainingMs = s.totalMs; } else { timerId = setInterval(tick, 250); lockScreen(); } }
  paintCount(); paint();
})();
