/* Drive-Energy-Doc-Panel: Fahrzeug-Reiter, Tankliste mit Belegfotos, Bearbeiten, CSV-Export */
const DEFW = { nr: 46 };   // Standardbreite einzelner Spalten in px (sonst 120 bei fester Breite)
const CURRENCIES = ["ALL", "AED", "AUD", "BAM", "BRL", "BYN", "CAD", "CHF", "CNY", "CZK", "DKK", "EGP", "GBP", "GEL", "HUF", "INR", "ISK", "JPY", "MAD", "MDL", "MKD", "MXN", "NOK", "NZD", "PLN", "RON", "RSD", "SEK", "THB", "TND", "TRY", "UAH", "USD", "ZAR"];
const FUEL_GRADES = { diesel: "Diesel", diesel_premium: "Diesel Premium", e10: "Super E10", e5: "Super E5", ron95: "Super 95", ron98: "Super 98", lpg: "LPG" };
const COLS = ["nr", "date", "km", "station", "qty", "price", "total", "cons", "receipt", "note", "act"];

const VERSION = "0.1.81";

class DriveEnergyDocPanel extends HTMLElement {
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._loadLang().then(() => this._load());
    this._subscribe();
  }

  _subscribe() {
    // Live-Ereignisse vom Server: ein Foto aus Telegram/WhatsApp wird verarbeitet (Hinweis), die Antwort kommt (Meldung), die Liste wird neu geladen
    if (this._sub || this._subBusy || !this._hass || !this._hass.connection || !this.isConnected) return;
    this._subBusy = true;
    this._hass.connection.subscribeMessage(ev => this._onEvent(ev), { type: "drive_energy_doc/subscribe" }).then(u => { this._sub = u; this._subBusy = false; }, () => { this._subBusy = false; });
  }

  _onEvent(ev) {
    if (!ev) return;
    if (ev.event === "processing") {
      if (ev.state === "start") this._liveBanner(true);
      else {
        this._liveBanner(false);
        if (ev.entry) this._jumpId = ev.entry;   // zur neuen Zeile springen und sie markieren
        this._load();
      }
    } else if (ev.event === "reply") {
      this._liveToast(ev.text || "");
    } else if (ev.event === "changed") {
      clearTimeout(this._chgT);
      this._chgT = setTimeout(() => this._load(), 600);   // mehrere Änderungen auf einmal: nur einmal neu laden
    }
  }

  _liveWrap() {
    // eigener Container für Hinweis und Meldung: ein Neuzeichnen der Liste (innerHTML) darf sie nicht löschen
    if (!this._liveEl) { this._liveEl = document.createElement("div"); this._liveEl.className = "livewrap"; }
    if (this.shadowRoot && this._liveEl.parentNode !== this.shadowRoot) this.shadowRoot.appendChild(this._liveEl);
    return this._liveEl;
  }

  _liveBanner(on) {
    const old = this._liveEl && this._liveEl.querySelector(".livebn");
    clearTimeout(this._bnT);
    if (!on) { if (old) old.remove(); return; }
    if (old || !this.shadowRoot) return;
    const b = document.createElement("div");
    b.className = "livebn";
    b.innerHTML = `<div class="spin"></div><div>${this.T("Foto wird gelesen …")}</div>`;
    this._liveWrap().appendChild(b);
    this._bnT = setTimeout(() => b.remove(), 240000);   // Sicherung, falls das Ende nie kommt
  }

  _liveToast(text) {
    if (!this.shadowRoot || !text) return;
    this._liveWrap().querySelectorAll(".livetoast").forEach(x => x.remove());
    const lines = String(text).split(/\n/).map(s => s.trim()).filter(Boolean);
    const t = document.createElement("div");
    t.className = "livetoast";
    t.innerHTML = `<button class="x" aria-label="OK">×</button>${lines.map((s, i) => `<div${i ? "" : ' class="h"'}>${this._esc(s)}</div>`).join("")}`;
    t.querySelector(".x").onclick = () => t.remove();
    this._liveWrap().appendChild(t);
    clearTimeout(this._toT);
    this._toT = setTimeout(() => t.remove(), 20000);
  }
  set narrow(v) { this._narrow = v; }
  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      // ShadowRoot kennt kein onclick: echten Listener setzen
      this.shadowRoot.addEventListener("click", ev => { if (this._cur) this._click(ev, this._cur); });
      document.addEventListener("keydown", ev => { if (this.isConnected) this._keys(ev); });
      this.shadowRoot.addEventListener("pointerdown", ev => this._rsStart(ev));
      // Beleg beim Darüberfahren vergrößern (Maus/Stift; am Handy gibt es den Foto-Viewer per Tipp)
      this.shadowRoot.addEventListener("pointerover", ev => {
        const t = ev.target;
        if (ev.pointerType !== "touch" && t.dataset && t.dataset.multi) this._selShow(t);
        else if (ev.pointerType !== "touch" && t.classList && t.classList.contains("thumb")) this._pvShow(t, ev);
        else if (ev.pointerType !== "touch") { const n = t.closest ? t.closest("[data-note]") : null; if (n) this._noteShow(n, true); }   // Notiz beim Darüberfahren zeigen
      });
      this.shadowRoot.addEventListener("pointerout", ev => {
        const n = ev.target.closest ? ev.target.closest("[data-note]") : null;
        if (n && this._noteEl) { this._noteEl.remove(); this._noteEl = null; }
      });
      this.shadowRoot.addEventListener("pointerout", ev => {
        if (ev.pointerType === "touch" || !ev.target.dataset || !ev.target.dataset.multi) return;
        setTimeout(() => { const pop = this.shadowRoot.querySelector(".pop.sel"); if (pop && !pop.matches(":hover")) pop.remove(); }, 450);
      });
      this.shadowRoot.addEventListener("pointermove", ev => { if (this._pvEl && ev.pointerType !== "touch") this._pvMove(ev); });
      this.shadowRoot.addEventListener("pointerout", ev => { if (ev.target.classList && ev.target.classList.contains("thumb")) this._pvHide(); });
      this.shadowRoot.addEventListener("dblclick", ev => {
        if (ev.target.classList && ev.target.classList.contains("rs")) {
          this._cw = {}; this._co = null;
          this._saveCw();
          this._hide = [];
          this._sort = null;
          try { localStorage.removeItem("deCo"); localStorage.removeItem("deHide"); localStorage.removeItem("deSort"); } catch (e) { /* ignore */ }
          this._render();
        }
      });
      // Reihenfolge wie im Device Inventory: Überschrift auf eine andere ziehen
      this.shadowRoot.addEventListener("mousedown", ev => { if (ev.target.classList && ev.target.classList.contains("rs")) ev.preventDefault(); });
      this.shadowRoot.addEventListener("dragstart", ev => {
        const th = ev.target.closest ? ev.target.closest("th[data-c]") : null;
        if (!th || th.dataset.c === "act") { ev.preventDefault(); return; }
        this._dragCol = th.dataset.c;
        ev.dataTransfer.effectAllowed = "move";
        try { ev.dataTransfer.setData("text/plain", this._dragCol); } catch (e) { /* ignore */ }
      });
      this.shadowRoot.addEventListener("dragover", ev => {
        const th = ev.target.closest ? ev.target.closest("th[data-c]") : null;
        if (!this._dragCol || !th || th.dataset.c === "act") return;
        ev.preventDefault();
        this.shadowRoot.querySelectorAll("th.dropt").forEach(x => { if (x !== th) x.classList.remove("dropt"); });
        th.classList.add("dropt");
      });
      this.shadowRoot.addEventListener("drop", ev => {
        const th = ev.target.closest ? ev.target.closest("th[data-c]") : null;
        const d = this._dragCol; this._dragCol = null;
        if (!d || !th || th.dataset.c === "act" || th.dataset.c === d) { this._render(); return; }
        ev.preventDefault();
        const o = this._order().slice(), from = o.indexOf(d), to = o.indexOf(th.dataset.c);
        o.splice(from, 1); o.splice(to, 0, d);
        this._co = o;
        try { localStorage.setItem("deCo", JSON.stringify(o)); } catch (e) { /* ignore */ }
        this._render();
      });
      this.shadowRoot.addEventListener("dragend", () => { this._dragCol = null; this.shadowRoot.querySelectorAll("th.dropt").forEach(x => x.classList.remove("dropt")); });
    }
    this._tab = 0;
    this._hide = [];
    try { this._hide = JSON.parse(localStorage.getItem("deHide") || "[]") || []; } catch (e) { /* ignore */ }
    this._sort = null;   // Sortierung per Klick auf die Spaltenüberschrift: {c: Spalte, dir: 1 aufsteigend | -1 absteigend}
    // Sortierung wird nicht gespeichert: beim Öffnen und beim Fahrzeugwechsel gilt immer der Standard (Nr. absteigend)
    this._cw = {};
    this._co = null;
    try { this._co = JSON.parse(localStorage.getItem("deCo") || "null"); } catch (e) { /* ignore */ }
    try { this._cw = JSON.parse(localStorage.getItem("deCw") || "{}") || {}; } catch (e) { /* ignore */ }
    this._ori = "portrait";
    this._rcp = true;
    try { if (localStorage.getItem("deRcp") === "0") this._rcp = false; } catch (e) { /* ignore */ }
    try { if (localStorage.getItem("deOri") === "landscape") this._ori = "landscape"; } catch (e) { /* ignore */ }
    this._render();
    this._timer = setInterval(() => this._load(), 60000);
    this._subscribe();   // beim Wiederöffnen der Seite
  }
  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._sub) { try { this._sub(); } catch (e) { /* ignore */ } this._sub = null; }
  }

  async _loadLang() {
    // Oberflächensprache = Sprache des HA-Benutzers; Wörterbuch i18n/<sprache>.json (Schlüssel = deutscher Text), Deutsch braucht keines
    const l = String((this._hass.locale && this._hass.locale.language) || this._hass.language || "en");
    const base = ({ no: "nb", nn: "nb", sh: "hr" })[l.toLowerCase().split("-")[0]] || l.toLowerCase().split("-")[0];
    this._locale = l;
    this._dict = {};
    this._rtl = ["ar", "he", "fa"].includes(base);
    if (base === "de") return;
    const get = async code => { try { const r = await fetch(`/drive_energy_doc_static/i18n/${code}.json?v=${VERSION}`); return r.ok ? await r.json() : null; } catch (e) { return null; } };
    this._dict = (await get(base)) || (await get("en")) || {};
  }
  T(s, ...a) {
    let r = (this._dict && this._dict[s]) || s;
    a.forEach((v, i) => { r = r.split(`{${i}}`).join(v); });
    return r;
  }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: "drive_energy_doc/list" });
      if (!this._tabInit) {   // beim ersten Laden das zuletzt gewählte Fahrzeug wieder auswählen
        this._tabInit = true;
        try {
          const i = this._data.findIndex(x => x.id === localStorage.getItem("deVeh"));
          if (i >= 0) this._tab = i;
        } catch (e) { /* ignore */ }
      }
      if (!this._dlg && !this.shadowRoot.querySelector(".busy, .dlg")) {   // nicht neu zeichnen, solange der Fortschritts- oder ein anderer Dialog offen ist
        this._render();
        if (this._jumpId) { const id = this._jumpId; this._jumpId = null; setTimeout(() => { const r = [...this.shadowRoot.querySelectorAll("tr[data-id]")].find(x => x.dataset.id === id); if (r) { this._selId = id; r.classList.add("rsel"); r.scrollIntoView({ block: "center", behavior: "smooth" }); } }, 50); }   // zur Zeile des gerade erfassten Belegs springen
      } else {   // ein Dialog ist offen: die neuen Daten liegen schon vor, gezeichnet wird nach dem Schließen (nicht verlieren)
        clearTimeout(this._retryT);
        this._retryT = setTimeout(() => this._load(), 2000);
      }
    } catch (e) { this._err = String(e.message || e); this._render(); }
  }
  _fmt(n, d = 2) { return n == null ? "–" : Number(n).toLocaleString(this._locale || "de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  _d(ts) { return new Date(ts * 1000).toLocaleDateString(this._locale || "de-DE", { dateStyle: "short" }); }
  _tm(ts) { return new Date(ts * 1000).toLocaleTimeString(this._locale || "de-DE", { timeStyle: "short" }); }
  _date(ts) { return this._d(ts) + ", " + this._tm(ts); }
  _gps(e, link = true) {
    if (e.lat == null || e.lon == null) return "";
    const txt = `${Number(e.lat).toFixed(5)}, ${Number(e.lon).toFixed(5)}`;
    return link ? `<a href="https://www.google.com/maps/search/?api=1&query=${e.lat},${e.lon}" target="_blank" rel="noopener">${txt}</a>` : txt;
  }
  _order() {
    // gespeicherte Reihenfolge, falls sie genau die bekannten Spalten enthält; „act“ (Knöpfe) bleibt immer ganz rechts
    const o = Array.isArray(this._co) ? this._co.filter(c => COLS.includes(c) && c !== "act") : [];
    COLS.filter(c => c !== "act").forEach(c => { if (!o.includes(c)) o.push(c); });
    if (o.includes("nr") && o[0] !== "nr") { o.splice(o.indexOf("nr"), 1); o.unshift("nr"); }   // Nummer steht immer vorn
    return [...o, "act"];
  }

  _pvShow(t, ev) {
    this._pvHide();
    const box = document.createElement("div");
    box.className = "pv";
    const img = document.createElement("img");
    img.src = t.dataset.p;
    img.onload = () => { if (this._pvEl === box && this._pvLast) this._pvMove(this._pvLast); };
    box.appendChild(img);
    this.shadowRoot.appendChild(box);
    this._pvEl = box;
    this._pvMove(ev);
  }

  _pvMove(ev) {
    const box = this._pvEl;
    if (!box) return;
    this._pvLast = { clientX: ev.clientX, clientY: ev.clientY };
    const r = box.getBoundingClientRect(), gap = 18;
    let x = ev.clientX + gap, y = ev.clientY + gap;
    if (x + r.width > window.innerWidth - 8) x = Math.max(8, ev.clientX - r.width - gap);   // links vom Zeiger, wenn rechts kein Platz ist
    if (y + r.height > window.innerHeight - 8) y = Math.max(8, window.innerHeight - r.height - 8);
    box.style.left = x + "px";
    box.style.top = y + "px";
  }

  _selShow(el) {
    const old = this.shadowRoot.querySelector(".pop"); if (old) old.remove();
    const e = ((this._cur && this._cur.entries) || []).find(x => x.id === el.dataset.multi);
    if (!e) return;
    const r = el.getBoundingClientRect(), pop = document.createElement("div");
    pop.className = "pop sel";
    pop.innerHTML = (e.photo_urls || []).map((p, i) => `<img src="${p}" data-p="${p}" data-entry="${e.id}" data-name="${this._esc((e.photos || [])[i] || "")}" alt="${this.T("Foto {0}", i + 1)}" title="${this.T("Foto {0}", i + 1)}">`).join("");
    pop.style.cssText = `position:fixed;z-index:98;padding:8px;border-radius:8px;background:var(--card-background-color);box-shadow:0 2px 12px #0006;border:1px solid var(--divider-color);top:${Math.min(r.bottom - 2, window.innerHeight - 90)}px;left:${Math.max(8, Math.min(r.left - 20, window.innerWidth - 380))}px`;
    pop.addEventListener("pointerleave", ev => { if (ev.pointerType !== "touch") pop.remove(); });
    this._pvHide();
    this.shadowRoot.append(pop);
  }

  _noteShow(t, hover) {
    const old = this.shadowRoot.querySelector(".pop"); if (old) old.remove();
    const r = t.getBoundingClientRect(), pop = document.createElement("div");
    pop.className = "pop"; pop.textContent = t.dataset.note;
    pop.style.cssText = `position:fixed;z-index:98;max-width:min(80vw,320px);padding:8px 12px;border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);box-shadow:0 2px 12px #0006;border:1px solid var(--divider-color);font-size:13px;white-space:pre-wrap;top:${r.bottom + 6}px;left:${Math.max(8, Math.min(r.left, window.innerWidth - 328))}px` + (hover ? ";pointer-events:none" : "");
    this.shadowRoot.append(pop);
    this._noteEl = hover ? pop : null;
  }

  _pvHide() {
    if (this._pvEl) { this._pvEl.remove(); this._pvEl = null; }
  }

  async _openPlate(v) {
    // Land und Kennzeichen wählen: Länderliste mit echt gezeichneten Schildern, das große Schild oben zeichnet sich sofort neu
    if (!this._countries) {
      try { this._countries = await this._hass.callWS({ type: "drive_energy_doc/countries" }); }
      catch (e) { alert(this.T("Länderliste nicht verfügbar: ") + (e.message || e)); return; }
    }
    this._pvHide();
    const st = { cc: v.plate_country || "DE", plate: v.plate || "", q: "" };
    const url = (cc, t) => `/api/drive_energy_doc/plate.svg?cc=${cc}&t=${encodeURIComponent(t)}`;
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card">
      <div class="dh">${this.T("Kennzeichen")} · ${this._esc(v.name)}</div>
      <img class="pvp" alt="${this.T("Vorschau")}">
      <input id="plt" type="text" maxlength="14" placeholder="${this.T("Kennzeichen")}" autocomplete="off" spellcheck="false">
      <input id="cf" type="search" placeholder="${this.T("Land suchen")}" autocomplete="off">
      <div class="cl"></div>
      <div class="df"><button data-d="cancel">${this.T("Abbrechen")}</button><button data-d="save" class="pri">${this.T("Speichern")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const prev = dlg.querySelector(".pvp"), inp = dlg.querySelector("#plt"), search = dlg.querySelector("#cf"), list = dlg.querySelector(".cl");
    inp.value = st.plate;
    const mark = () => list.querySelectorAll(".cty").forEach(b => b.classList.toggle("on", b.dataset.cc === st.cc));
    const draw = () => { prev.src = url(st.cc, st.plate); mark(); };
    const fill = () => {
      const q = st.q.trim().toLowerCase();
      list.innerHTML = this._countries.filter(c => !q || c.name.toLowerCase().includes(q) || c.code.toLowerCase() === q || c.cc.toLowerCase() === q)
        .map(c => `<button class="cty" data-cc="${c.cc}" title="${this._esc(c.name)}"><img loading="lazy" alt="" src="${url(c.cc, c.example)}"><span>${this._esc(c.name)}</span></button>`).join("");
      draw();
      const on = list.querySelector(".cty.on"); if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest" });
    };
    const close = () => { dlg.remove(); this._dlg = null; this._load(); };
    inp.oninput = () => { st.plate = inp.value; draw(); };
    search.oninput = () => { st.q = search.value; fill(); };
    list.onclick = ev => { const b = ev.target.closest(".cty"); if (b) { st.cc = b.dataset.cc; draw(); } };
    dlg.onclick = async ev => {
      ev.stopPropagation();
      const b = ev.target.closest("[data-d]");
      if (b && b.dataset.d === "cancel" || ev.target === dlg) return close();
      if (b && b.dataset.d === "save") {
        try { await this._hass.callWS({ type: "drive_energy_doc/set_plate", vehicle: v.id, plate: st.plate, country: st.cc }); }
        catch (e) { alert(this.T("Speichern fehlgeschlagen: ") + (e.message || e)); return; }
        close();
      }
    };
    dlg.onkeydown = ev => { if (ev.key === "Escape") close(); };
    fill();
    inp.focus();
  }

  _saveCw() {
    try { localStorage.setItem("deCw", JSON.stringify(this._cw)); } catch (e) { /* ignore */ }
  }

  _rsStart(ev) {
    const h = ev.target;
    if (!h.classList || !h.classList.contains("rs")) return;
    ev.preventDefault();
    const root = this.shadowRoot, tbl = root.querySelector("table");
    const ths = [...root.querySelectorAll("th[data-c]")];
    // erster Zug: alle Spalten auf ihre aktuelle Breite festschreiben, dann nur die gezogene ändern
    ths.forEach(th => { if (!this._cw[th.dataset.c]) this._cw[th.dataset.c] = th.offsetWidth; });
    const key = h.dataset.c, x0 = ev.clientX, w0 = this._cw[key];
    h.classList.add("on");
    tbl.classList.add("fx");
    const apply = () => {
      COLS.forEach(c => { const col = root.querySelector(`col[data-c="${c}"]`); if (col) col.style.width = this._cw[c] + "px"; });
      tbl.style.width = [...root.querySelectorAll("col[data-c]")].reduce((t, col) => t + (this._cw[col.dataset.c] || DEFW[col.dataset.c] || 120), 0) + "px";
    };
    apply();
    const mv = e => { this._cw[key] = Math.max(36, Math.round(w0 + e.clientX - x0)); apply(); };
    const up = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
      h.classList.remove("on"); this._saveCw();
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  }

  _pic(v) {
    // Fahrzeugbild: hochgeladenes Bild, sonst Bild-Entität
    return v.image_url || (v.image && this._hass.states[v.image] ? this._hass.states[v.image].attributes.entity_picture : "") || "";
  }
  _title(v) {
    // Überschrift: Fahrzeugtyp (z. B. „BMW X1 xDrive20d“); enthält er den Namen nicht, steht „Name · Typ“
    const n = v.name || "", t = (v.type || "").trim();
    if (!t) return n;
    return t.toLowerCase().includes(n.toLowerCase()) ? t : `${n} · ${t}`;
  }
  _plate(v, small = false) {
    // Dasselbe gezeichnete Schild wie in den Dialogen (mit Länderstreifen, Europa-Ring bei EU-Ländern)
    const src = `/api/drive_energy_doc/plate.svg?cc=${encodeURIComponent(v.plate_country || "DE")}&t=${encodeURIComponent(v.plate)}`;
    return `<img class="plateimg${small ? " tabplate" : ""}" src="${src}" alt="${this._esc(v.plate)}" title="${this._esc(v.plate)}">`;
  }
  _warnText(w, col) {
    if (w.k === "missing") return this.T("Angabe fehlt");
    const f = (x, d = 2) => this._fmt(x, d);
    let d = "";
    if (w.k === "calc") d = `${f(w.q)} × ${f(w.p, 3)} = ${f(w.calc)} ≠ ${f(w.t)} €`;
    else if (w.k === "combined") d = `${f(w.v, 1)} kWh/100 km (> ${f(w.hi, 0)})`;
    else if (w.k === "dup") d = `= ${this.T("Nr.")} ${(this._nums && this._nums[w.other]) || "?"}`;
    else if (w.k === "range") d = `${f(w.v, col === "price" ? 3 : 2)} (${f(w.lo)} – ${f(w.hi)})`;
    else if (w.k === "cap") d = `${f(w.v)} > ${f(w.cap, 0)}`;
    else if (w.k === "back") d = `< ${f(w.prev, 0)} km`;
    else if (w.k === "jump") d = `+${f(w.d, 0)} km`;
    return this.T("Unplausibler Wert") + ": " + d;
  }

  _warn(e, col, v) {
    // Warndreieck mit Erklärung (Zahlen, sprachneutral) bei einem unplausiblen Wert, Fragezeichen bei einer fehlenden Angabe; die Prüfung macht der Server (stats.plausibility).
    // Ein Klick öffnet die Erklärung mit „Quittieren“.
    const w = e.warn && e.warn[col];
    if (!w) return "";
    const txt = this._esc(this._warnText(w, col)), at = `data-wid="${e.id}" data-wcol="${col}" role="button" tabindex="0"`;
    if (w.k === "missing") return ` <span class="wq" ${at} title="${txt}" aria-label="${txt}">${this._ico("help")}</span>`;
    return ` <span class="wtri" ${at} title="${txt}" aria-label="${txt}">${this._ico("warn")}</span>`;
  }

  _ackDlg(v, id, col) {
    const e = v.entries.find(x => x.id === id), w = e && e.warn && e.warn[col];
    if (!w) return;
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.style.zIndex = 110;
    dlg.innerHTML = `<div class="card"><div class="dh">${this._ico(w.k === "missing" ? "help" : "warn")} ${this._esc(this._warnText(w, col))}</div><div class="df"><button data-d="x">${this.T("Abbrechen")}</button><button data-d="ok" class="pri">${this.T("Quittieren")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    dlg.onclick = async ev => {
      ev.stopPropagation();
      const b = ev.target.closest("[data-d]");
      if (!b && ev.target !== dlg) return;
      if (b && b.dataset.d === "ok") { try { await this._hass.callWS({ type: "drive_energy_doc/ack", vehicle: v.id, entry: id, column: col }); } catch (err) { alert(this.T("Fehler") + ": " + (err.message || err)); } this._load(); }
      dlg.remove();
    };
    dlg.querySelector("[data-d=ok]").focus();
  }

  _ico(n) {
    // Einfarbige Linien-Symbole (currentColor): schwarz im hellen, weiß im dunklen Design
    const P = {
      csv: '<path d="M12 4v10M7.5 10 12 14.5 16.5 10M5 19h14"/>',
      print: '<rect x="3" y="10" width="18" height="7" rx="1.5"/><path d="M7 17v3h10v-3"/><rect x="7" y="3" width="10" height="7"/>',
      portrait: '<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M14 3v5h5"/>',
      landscape: '<path d="M3 7a2 2 0 0 1 2-2h11l5 5v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M16 5v5h5"/>',
      photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 16l-5-5-8 8"/>',
      photoOff: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 16l-5-5-8 8"/><path d="M3.5 3.5l17 17"/>',
      plate: '<rect x="2.5" y="7" width="19" height="10" rx="2"/><path d="M6.5 7v10"/><path d="M10 12h8"/>',
      plus: '<path d="M12 5v14M5 12h14"/>',
      camera: '<path d="M4 8h3l1.5-2h7L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.2"/>',
      edit: '<path d="M4 20l1-4L16.5 4.5l3 3L8 19l-4 1zM14 7l3 3"/>',
      trash: '<path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13M10 11v6M14 11v6"/>',
      cols: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
      note: '<path d="M5 4h14v12h-9l-5 4zM8.5 8.5h7M8.5 12h5"/>',
      warn: '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v5M12 17.6v.4"/>',
      help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.6a2.6 2.6 0 1 1 3.7 2.3c-.8.4-1.2 1-1.2 2M12 17v.4"/>',
      close: '<path d="M6 6l12 12M18 6L6 18"/>',
      warn: '<path d="M12 4l9 16H3zM12 10v5M12 17.2v.3"/>',
    };
    return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;
  }
  _esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  _render() {
    this._render0();
    if (this._liveEl && this._liveEl.childElementCount) this._liveWrap();   // Hinweis/Meldung nach dem Neuzeichnen wieder einhängen
  }

  _render0() {
    if (!this.shadowRoot) return;
    const d = this._data || [];
    const v = d[this._tab] || d[0];
    const css = `
      :host{display:block;padding:16px;color:var(--primary-text-color);background:var(--primary-background-color);min-height:100%;box-sizing:border-box}
      .head{display:flex;justify-content:flex-start;align-items:center;gap:28px;margin-bottom:12px;flex-wrap:wrap}
      h1{font-size:26px;line-height:1.15;margin:0;font-weight:500}
      .app{font-size:12px;letter-spacing:.6px;text-transform:uppercase;color:var(--secondary-text-color)}
      .logo{height:40px;width:40px}
      .ttl{display:flex;align-items:center;gap:16px;flex-wrap:nowrap;min-width:0}
      @media(max-width:520px){.ttl{flex-wrap:wrap}}
      .plate{white-space:nowrap;flex:none}
      .chip{flex:none;white-space:nowrap;background:var(--primary-color);color:var(--text-primary-color,#fff);border-radius:10px;padding:6px 14px;font-size:16px}
      .plateimg{height:40px;width:auto;flex:none}
      .head.pick{cursor:pointer}.chev{font-size:18px;color:var(--secondary-text-color);font-weight:400}
      .vopic{margin-left:auto;height:34px;max-width:30%;object-fit:contain;flex:none}
      .vo{display:flex;align-items:center;gap:14px;padding:10px 12px;border-radius:10px;cursor:pointer;border:2px solid transparent}.vo:hover{background:var(--secondary-background-color,#0001)}.vo.on{border-color:var(--primary-color)}.vo .nm{font-size:13px;color:var(--secondary-text-color)}.vo .tt{font-size:16px}
      .vsel{display:inline-flex;align-items:center;gap:10px;cursor:pointer;opacity:.55;transition:opacity .15s;padding:4px 6px;border-radius:10px}.vsel:hover{opacity:.85}.vsel.on{opacity:1}
      .tabplate{height:34px;border-radius:7px}.vsel.on .tabplate{outline:3px solid var(--primary-color);outline-offset:2px}
      .vtype{font-size:15px}.vsel.on .vtype{font-weight:600}
      .plate{display:inline-flex;align-items:stretch;border:2px solid #111;border-radius:6px;background:#fff;color:#111;font:600 16px/1.5 Arial,sans-serif;letter-spacing:1px;overflow:hidden}
      .plate i{display:flex;align-items:center;justify-content:center;min-width:16px;padding:0 5px;background:#003399;color:#fff;font:600 10px/1 Arial,sans-serif;font-style:normal;letter-spacing:0}
      .plate b{font-weight:600;padding:0 12px}
      .plate.nl,.plate.gb{background:#f7c600}
      .plate.ch i,.plate.us i{display:none}
      .plate.us b{color:#1b3a73}
      .car{max-height:96px;max-width:45%;object-fit:contain}
      .tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
      button{display:inline-flex;align-items:center;gap:5px;font:inherit;cursor:pointer;border:1px solid var(--divider-color);background:var(--card-background-color);color:inherit;border-radius:8px;padding:6px 12px}
      button.on{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color)}
      .sum{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
      .sum div{background:var(--card-background-color);border-radius:10px;padding:10px 14px;min-width:120px}
      .sum b{display:block;font-size:20px}
      .sum .shoot{flex:0 1 auto;min-width:120px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;background:var(--primary-color);color:var(--text-primary-color,#fff);border:0;border-radius:10px;padding:10px 18px;font:inherit;cursor:pointer;min-height:104px}
      .sum .shoot .ico{width:44px;height:44px}.sum .shoot span{font-size:13px;color:inherit}
      .stat{display:inline-flex;flex-direction:column;justify-content:center;padding:2px 14px;white-space:nowrap}.stat b{font-size:18px;font-weight:600;color:var(--primary-text-color)}.stat span{font-size:12px;color:var(--secondary-text-color)}
      .sum span{font-size:12px;color:var(--secondary-text-color)}
      .wrap{overflow:auto;background:var(--card-background-color);border-radius:10px}
      table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.3}
      th,td{padding:4px 8px;text-align:left;border-bottom:1px solid var(--divider-color);white-space:nowrap}
      td.n,th.n{text-align:right}
      th.sortable{cursor:pointer;user-select:none}th.sortable:hover{background:var(--secondary-background-color,#f1f1f1)}.si{font-size:10px;margin-left:5px;opacity:.75}
      th{position:sticky;top:0;background:var(--card-background-color);font-weight:500}
      .src{font-size:11px;color:var(--secondary-text-color)}
      .tag{display:inline-block;padding:0 7px;border-radius:9px;background:#0ea5e9;color:#fff;font-size:11px;vertical-align:middle;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;box-sizing:border-box}
      .gps{font-size:10px;opacity:.85}.gps a{color:inherit}
      .thumb{height:28px;width:28px;object-fit:cover;border-radius:4px;margin-right:3px;vertical-align:middle;cursor:pointer}
      .no{color:var(--secondary-text-color);display:inline-flex;vertical-align:middle}
      .lb{position:fixed;inset:0;background:#000d;display:flex;align-items:center;justify-content:center;z-index:99}
      .lb img{max-width:92vw;max-height:92vh}
      .ico{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
      button small{font-size:11px;letter-spacing:.3px}
      th{position:relative}
      .ver{margin-top:10px;font-size:11px;color:var(--secondary-text-color);opacity:.7}
      .dlg{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:100}
      .dlg .card{background:var(--card-background-color,#fff);color:var(--primary-text-color);border-radius:14px;padding:16px;width:min(620px,94vw);max-height:90vh;display:flex;flex-direction:column;gap:10px;box-sizing:border-box}
      .dh{font-size:18px;font-weight:500}
      .pvp{height:60px;align-self:flex-start}
      .res .card{width:min(540px,94vw);gap:12px;padding:18px;max-height:92vh;max-height:92dvh;overflow:hidden}.res .bd{display:flex;flex-direction:column;gap:14px;overflow:auto;min-height:0;flex:1 1 auto}.res .ask{font-size:16px;font-weight:600;line-height:1.4}.res .mid{flex-wrap:wrap;justify-content:center}.res .mid>*{min-width:0}.res .rows{overflow-wrap:anywhere;flex:1 1 220px}.res .df{flex:none;flex-wrap:wrap}
      .res .hd{display:flex;align-items:center;gap:16px}.res .ttl{font-size:20px;font-weight:600;line-height:1.3}
      .res .mark{flex:none;width:52px;height:52px;border-radius:50%;background:#2e9e5b;color:#fff;font-size:30px;display:flex;align-items:center;justify-content:center}.res .mark.q{background:var(--primary-color)}.res .mark.w{background:var(--warning-color,#f59e0b)}
      .res .mid{display:flex;align-items:center;gap:16px}.res .rshot{height:110px;max-width:34%;object-fit:cover;border-radius:8px;box-shadow:0 1px 5px #0004}
      .res .rows{flex:1;background:var(--secondary-background-color,#f1f1f1);border-radius:10px;padding:10px 14px;font-size:18px;line-height:1.65}.res .rows div:last-child{font-weight:600;font-size:20px}
      .res .rpic{max-height:64px;max-width:28%;object-fit:contain;flex:none}.res #ra{font-size:17px;padding:12px}
      .smlist{display:flex;flex-direction:column;gap:10px;max-height:52vh;overflow:auto}.sm{display:flex;gap:12px;align-items:center;background:var(--secondary-background-color,#f1f1f1);border-radius:10px;padding:8px 10px}.sm img{height:64px;width:48px;object-fit:cover;border-radius:6px;flex:none}.smr{font-size:13px;color:var(--secondary-text-color);margin-top:2px}
      .smwarn{background:rgba(255,160,0,.15);border-radius:10px;padding:8px 12px;font-size:14px;line-height:1.5;max-height:20vh;overflow:auto}
      .res .df button{font-size:17px;padding:10px 28px}
      .busy{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:120}
      .busy .card{background:var(--card-background-color,#fff);color:var(--primary-text-color);border-radius:14px;padding:22px 28px;display:flex;flex-direction:column;align-items:center;gap:14px;font-size:16px;max-width:min(90vw,420px)}
      .busy .brow{display:flex;align-items:center;gap:16px}.bpic{max-width:100%;max-height:90px;object-fit:contain}.bplate{display:flex;justify-content:center;margin-top:-4px}.bplate .plateimg{height:38px;width:auto}
      .scan{position:relative;line-height:0;border-radius:8px;overflow:hidden;box-shadow:0 1px 6px #0004}.scan img{max-width:min(78vw,340px);max-height:min(38vh,300px);object-fit:contain;display:block}
      .lupe{position:absolute;width:76px;height:76px;left:8%;top:6%;animation:lupe 4.2s ease-in-out infinite;filter:drop-shadow(0 3px 4px #0006)}
      @keyframes lupe{0%{left:6%;top:4%}20%{left:52%;top:10%}40%{left:20%;top:34%}60%{left:56%;top:46%}80%{left:14%;top:62%}100%{left:6%;top:4%}}
      .pstrip{display:flex;gap:6px;flex-wrap:wrap;justify-content:center;max-width:100%}.pt{position:relative;width:42px;height:56px;border-radius:6px;overflow:hidden;opacity:.45;border:2px solid transparent}.pt img{width:100%;height:100%;object-fit:cover;display:block}.pt.cur{opacity:1;border-color:var(--primary-color)}.pt.done{opacity:.9}.pt b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(40,160,80,.55);color:#fff;font-size:22px}
      .pbar{width:100%;height:6px;border-radius:3px;background:var(--divider-color);overflow:hidden}.pbar i{display:block;height:100%;background:var(--primary-color);transition:width .3s}
      .stopb{font:inherit;font-size:15px;padding:8px 22px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color,#fff);color:var(--primary-text-color);cursor:pointer}
      .spin{width:26px;height:26px;border:4px solid var(--divider-color);border-top-color:var(--primary-color);border-radius:50%;animation:sp 1s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
      .ck{display:flex;align-items:center;gap:12px;padding:8px 4px;font-size:16px;cursor:pointer}.ck input{padding:0;width:20px;height:20px;border:0;background:none;accent-color:var(--primary-color)}
      .form .card{width:min(400px,94vw);padding:16px;gap:10px;max-height:92vh;max-height:92dvh;overflow:hidden}.form .bd{display:flex;flex-direction:column;gap:9px;overflow:auto;min-height:0;flex:1 1 auto;padding:2px}.form .dh{font-size:20px;font-weight:600}.form .g2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:9px 10px}.form .pr{display:flex;gap:6px}.form .fl .pr input{flex:1 1 0;width:0;min-width:0}.form .fl .pr select{flex:none;width:76px;padding:8px 4px}
      .phn{font-size:14px;color:var(--secondary-text-color)}
      .spin{width:44px;height:44px;border:5px solid var(--divider-color);border-top-color:var(--primary-color);border-radius:50%;animation:dspin 1s linear infinite}@keyframes dspin{to{transform:rotate(360deg)}}
      .form .fl{display:flex;flex-direction:column;gap:5px;font-size:14px;color:var(--secondary-text-color)}.form .fl input,.form .fl textarea{font-size:16px;padding:8px 10px;color:var(--primary-text-color);width:100%;box-sizing:border-box;min-height:0}.form .fl input[type=datetime-local]{min-height:40px}.form .fl textarea{min-height:60px}.form .fl select{font:inherit;font-size:16px;padding:8px 10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--primary-background-color);color:var(--primary-text-color);width:100%;box-sizing:border-box;min-height:40px}.form .hint{font-size:13px;color:var(--secondary-text-color);margin-top:-8px}.form .df{flex:none}.form .df button{font-size:16px;padding:8px 22px}.form .df button.ico{flex:0 0 92px;width:92px;min-height:58px;padding:0}.form .df button.ico svg{width:40px;height:40px;stroke-width:1.6}
      .dlg textarea{font:inherit;min-height:120px;padding:8px 10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--primary-background-color);color:inherit;resize:vertical}
      .dlg .big{justify-content:center;font-size:17px;padding:16px 12px}
      .dlg input{font:inherit;padding:8px 10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--primary-background-color);color:inherit}
      .cl{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;overflow:auto;max-height:44vh;padding:2px}
      .cty{display:flex;flex-direction:column;align-items:flex-start;gap:4px;padding:8px;border-radius:10px;text-align:left}
      .cty img{height:32px;max-width:100%}
      .cty span{font-size:12px;color:var(--secondary-text-color)}
      .cty.on{outline:2px solid var(--primary-color);outline-offset:0}
      .df{display:flex;justify-content:flex-end;gap:8px}
      .df button.ico{flex:0 0 72px;width:72px;min-width:0;min-height:52px;padding:0;display:flex;align-items:center;justify-content:center;margin-right:auto}.df button.ico svg{width:30px;height:30px}
      button.pri{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);border-color:var(--primary-color,#03a9f4)}
      .pv{position:fixed;z-index:98;pointer-events:none;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ccc);border-radius:8px;padding:4px;box-shadow:0 6px 24px rgba(0,0,0,.35);left:0;top:0}
      .pv img{display:block;max-width:min(440px,60vw);max-height:min(72vh,560px);border-radius:4px}
      .rs{position:absolute;top:0;right:-3px;bottom:0;width:8px;cursor:col-resize;user-select:none;touch-action:none;z-index:2}
      .rs::after{content:"";position:absolute;left:3px;top:18%;bottom:18%;width:1px;background:var(--secondary-text-color);opacity:.5}
      .sel{display:flex;gap:6px;flex-wrap:wrap;max-width:min(80vw,360px)}.sel img{height:64px;width:64px;object-fit:cover;border-radius:6px;cursor:pointer;border:1px solid var(--divider-color)}
      .rs:hover,.rs.on{background:var(--primary-color);opacity:.45}
      th[draggable=true]{cursor:grab}
      th.dropt{outline:2px dashed var(--primary-color);outline-offset:-2px}
      table.fx{table-layout:fixed}
      table.fx td,table.fx th{overflow:hidden;text-overflow:ellipsis}
      tbody tr{cursor:pointer}tbody tr:hover{background:color-mix(in srgb,var(--primary-color) 8%,var(--card-background-color))}
      tbody tr.ex,tbody tr.ex:hover{background:color-mix(in srgb,var(--warning-color,#ff9800) 20%,var(--card-background-color))}
      tbody tr.rsel,tbody tr.rsel:hover{background:color-mix(in srgb,var(--primary-color) 30%,var(--card-background-color));outline:2px solid var(--primary-color);outline-offset:-2px}
      tbody tr.rsel td:first-child{box-shadow:inset 5px 0 0 var(--primary-color)}
      .livebn{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:130;display:flex;align-items:center;gap:12px;padding:12px 18px;border-radius:12px;background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 4px 18px rgba(0,0,0,.35);font-size:16px}
      .livetoast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:130;width:min(560px,92vw);padding:14px 38px 14px 16px;border-radius:12px;background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 4px 18px rgba(0,0,0,.4);border-left:6px solid var(--primary-color);font-size:15px;line-height:1.4;box-sizing:border-box}
      .livebn .spin{width:26px;height:26px;border-width:4px}
      .livetoast .h{font-weight:600;margin-bottom:4px}.livetoast .x{position:absolute;top:6px;right:8px;border:0;background:none;color:inherit;font-size:24px;cursor:pointer;line-height:1}
      .wq{display:inline-flex;vertical-align:middle;color:var(--secondary-text-color);cursor:help}.wq .ico{width:16px;height:16px;stroke-width:2}
      td.est{color:var(--secondary-text-color);font-style:italic}
      .wtri{display:inline-flex;vertical-align:middle;color:var(--warning-color,#e67e22);cursor:help}.wtri .ico{width:16px;height:16px;stroke-width:2.2}
      .bar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}
      .bar button[data-act=add]{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color);padding:8px 14px}.bar button[data-act=add] .ico{width:30px;height:30px;stroke-width:2.6}
      td.nr{color:var(--secondary-text-color);font-size:12px}
      .tm{display:block;color:var(--secondary-text-color);font-size:12px}
      td[data-c=station] .src{display:inline}td[data-c=station] .src.gps{margin-left:8px}
      td[data-c=act] button{padding:3px 7px}td[data-c=act] .ico{width:18px;height:18px}
      .notec{cursor:pointer}.notei{display:inline-flex;cursor:pointer;opacity:.8}.notei:hover{opacity:1}.notei .ico{width:20px;height:20px}
      @media(max-width:700px){
        :host{padding:8px}
        .head{gap:8px}
        .sum{gap:6px;margin-bottom:8px}.sum div,.sum .shoot{flex:1 1 40%;min-width:0;padding:6px 10px}.sum .shoot{min-height:84px}.sum b{font-size:16px}
        .bar{margin-bottom:8px}
        .wrap{background:none;overflow:visible}
        table,table.fx{display:block;width:100%!important}
        colgroup,thead{display:none}
        tbody{display:block}
        tr{display:grid;grid-template-columns:64px 1fr auto auto;justify-content:stretch;align-items:center;gap:1px 10px;margin-bottom:6px;padding:7px 10px;background:var(--card-background-color);border-radius:10px;
           grid-template-areas:"date station station total" "qty price km cons" "receipt note act act"}
        td,td.n{display:block;padding:0;border:0;white-space:normal;text-align:left;overflow:visible!important;text-overflow:clip!important;min-width:0}
        td:empty{display:none}
        td[data-c=nr]{display:none}
        td[data-c=date]::before{content:attr(data-nr);display:block;font-weight:600;color:var(--primary-text-color)}
        td[data-c=date]{grid-area:date;color:var(--secondary-text-color);font-size:12px;line-height:1.25}
        .tm{display:block}.tm::before{content:none}
        td[data-c=total]{grid-area:total;text-align:right;font-size:16px;font-weight:600}
        td[data-c=station]{grid-area:station;font-size:13px;line-height:1.25}
        td[data-c=station] .gps,td[data-c=qty] .src,td[data-c=price] .src{display:none}
        td[data-c=qty]{grid-area:qty}td[data-c=price]{grid-area:price}td[data-c=km]{grid-area:km}td[data-c=cons]{grid-area:cons}
        td[data-c=qty],td[data-c=price],td[data-c=km],td[data-c=cons]{font-size:12px;color:var(--secondary-text-color)}
        td[data-c=price]::after{content:" €"}td[data-c=km]::after{content:" km"}td[data-c=cons]::after{content:" /100 km"}
        td[data-c=receipt]{grid-area:receipt;padding-top:4px}td[data-c=note]{grid-area:note;padding-top:4px;font-size:12px}
        td[data-c=act]{grid-area:act;justify-self:end;padding-top:4px;white-space:nowrap}
        td[data-c=act] button{padding:3px 7px}
      }
    `;
    this._pvHide();
    if (this._err) { this.shadowRoot.innerHTML = `<style>${css}</style><p>${this._esc(this._err)}</p>`; return; }
    if (!d.length) { this.shadowRoot.innerHTML = `<style>${css}</style><h1>Drive Energy Doc</h1><p>${this.T("Noch kein Fahrzeug. Einstellungen → Geräte & Dienste → Integration „Drive Energy Doc“ hinzufügen.")}</p>`; return; }
    const s = v.summary, u = this.T(v.unit);
    const pic = this._pic(v);
    const cw = this._cw || {};
    const fixed = COLS.some(c => cw[c]);
    const order = this._order().filter(c => c === "act" || !this._hide.includes(c));   // ausgeblendete Spalten weglassen
    const sumW = order.reduce((t, c) => t + (cw[c] || DEFW[c] || 120), 0);
    const nums = {};
    [...v.entries].filter(x => x.kind !== "extra").sort((a, b) => a.ts - b.ts).forEach((x, i) => { nums[x.id] = i + 1; });
    this._nums = nums;   // für die Hinweise der Warndreiecke (z. B. „doppelt zu Nr. 4“)   // laufende Nummer der Tankvorgänge, ältester = 1
    const sk = this._sort && COLS.includes(this._sort.c) ? this._sort : { c: "nr", dir: -1 };   // Standard: nach Nummer absteigend (neueste oben)
    const nrKey = {};   // Zubehör hat keine Nummer: es steht direkt hinter dem davor liegenden Tankvorgang, damit die Reihenfolge zeitlich stimmt
    { let last = 0; [...v.entries].sort((a, b) => a.ts - b.ts).forEach(x => { if (nums[x.id]) last = nums[x.id]; nrKey[x.id] = nums[x.id] || last + 0.5; }); }
    const skey = (e, c) => ({ nr: nrKey[e.id], date: e.ts, km: e.odometer, station: (e.station || "").toLowerCase(), qty: e.quantity, price: e.unit_price, total: e.total, cons: e.consumption, receipt: (e.photo_urls || []).length, note: (e.note || "").toLowerCase() })[c];
    const none = x => x == null || x === "" || (typeof x === "number" && isNaN(x));
    const list = [...v.entries].sort((a, b) => {   // leere Werte stehen immer unten, egal in welche Richtung
      const x = skey(a, sk.c), y = skey(b, sk.c);
      if (none(x) && none(y)) return 0;
      if (none(x)) return 1;
      if (none(y)) return -1;
      return (typeof x === "string" ? x.localeCompare(y, this._locale || "de") : x - y) * sk.dir;
    });
    const rows = list.map(e => {
      const cell = {
        nr: `<td class="n nr">${nums[e.id] || ""}</td>`,
        date: `<td data-nr="${nums[e.id] ? "#" + nums[e.id] : ""}"><span>${this._d(e.ts)}</span><span class="tm">${this._tm(e.ts)}</span></td>`,
        km: `<td class="n${e.odometer_source === "bekannt" ? " est" : ""}"${e.odometer_source === "bekannt" ? ` title="${this._esc(this.T("Kilometerstand"))} (≈)"` : ""}>${e.odometer != null ? this._fmt(e.odometer, 0) : "–"}${this._warn(e, "km", v)}</td>`,
        station: `<td><div>${this._esc(e.station || "")}</div><div class="src">${this._esc(e.address || "")}</div><div class="src gps">${this._gps(e)}</div></td>`,
        qty: `<td class="n">${e.quantity != null ? this._fmt(e.quantity) + " " + (e.kind === "extra" ? (e.unit || "") : (v.phev && e.energy === "electric" ? "kWh" : u)) : "–"}<div class="src">${e.fuel && e.kind !== "extra" ? this._esc(FUEL_GRADES[e.fuel] || "") + " " : ""}${e.level_from != null && e.level_to != null ? Math.round(e.level_from) + "→" + Math.round(e.level_to) + " %" : (e.increase != null ? "+" + Math.round(e.increase) + " %" : "")} ${this._esc(this.T(e.quantity_source || ""))}</div></td>`,
        price: `<td class="n">${this._fmt(e.unit_price, 3)}${this._warn(e, "price", v)}<div class="src">${this._esc(this.T(e.price_source || ""))}</div></td>`,
        total: `<td class="n">${this._fmt(e.total)} €${this._warn(e, "total", v)}</td>`,
        cons: `<td class="n">${e.consumption != null ? this._fmt(e.consumption) + (v.phev ? `<div class="src">${e.energy === "electric" ? "kWh" : u}/100 ${this.T("km")}</div>` : "") : "–"}${this._warn(e, "cons", v)}</td>`,
        receipt: (() => { const ph = e.photo_urls || [], im = (p, k) => `<img class="${k}" src="${p}" data-p="${p}" data-entry="${e.id}" data-name="${this._esc((e.photos || [])[ph.indexOf(p)] || "")}"${ph.length > 1 && k === "thumb" ? ` data-multi="${e.id}"` : ""} alt="${ph.indexOf(p) === 0 && e.receipt ? this.T("Beleg") : this.T("Zusatzfoto")}">`; return `<td>${ph.length ? im(ph[0], "thumb") : ""}${e.receipt ? "" : `<span class="no" title="${this.T("Beleg fehlt")}">${this._ico("warn")}</span>`}</td>`; })(),
        note: (() => { const full = [e.kind === "extra" ? (e.item || this.T("Zubehör")) : "", e.note || ""].filter(Boolean).join("\n"); return `<td>${full ? `<span class="notec" data-note="${this._esc(full)}">` : ""}${e.kind === "extra" ? `<span class="tag">${this._esc(e.item || this.T("Zubehör"))}</span> ` : ""}${e.note ? `<span class="notei" tabindex="0" role="button" aria-label="${this.T("Notiz anzeigen")}">${this._ico("note")}</span>` : ""}${full ? "</span>" : ""}</td>`; })(),
        act: `<td><button data-act="edit" title="${this.T("Bearbeiten")}" aria-label="${this.T("Bearbeiten")}">${this._ico("edit")}</button> <button data-act="del" title="${this.T("Eintrag löschen")}" aria-label="${this.T("Eintrag löschen")}">${this._ico("trash")}</button></td>`,
      };
      return `<tr data-id="${e.id}" class="${e.kind === "extra" ? "ex" : ""}${this._selId === e.id ? " rsel" : ""}">${order.map(k => cell[k].replace("<td", `<td data-c="${k}"`)).join("")}</tr>`;
    }).join("");
    this.shadowRoot.innerHTML = `<style>${css}</style>
      <div class="head${d.length > 1 ? " pick" : ""}"${d.length > 1 ? ` role="button" tabindex="0"` : ""}><div class="ttl"><img class="logo" src="/drive_energy_doc_static/icon.png?v=${VERSION}" alt=""><div><div class="app">Drive Energy Doc</div><h1>${this._esc(this._title(v))}${d.length > 1 ? ` <span class="chev">▾</span>` : ""}</h1></div>${v.plate ? this._plate(v) : ""}</div>${pic ? `<img class="car" src="${pic}" alt="${this._esc(v.name)}">` : ""}</div>
      <div class="sum">
        <div><b>${this._fmt(s.avg_consumption)}</b><span>${u}/100 ${this.T("km")} (${this.T("Ø letzte 5")})</span></div>
        ${v.phev ? `<div><b>${this._fmt(s.avg_consumption_electric)}</b><span>kWh/100 ${this.T("km")} (${this.T("Ø letzte 5")})</span></div>` : ""}
        <div><b>${this._fmt(s.cost_12m)} €</b><span>${this.T("Kosten 12 Monate")}</span></div>
        <button class="shoot" data-act="shoot" title="${this.T("Beleg fotografieren oder hochladen")}" aria-label="${this.T("Beleg fotografieren")}">${this._ico("camera")}<span>${this.T("Beleg / km Stand fotografieren")}</span></button>
      </div>
      <div class="bar"><button data-act="csv" title="${this.T("CSV-Export")}" aria-label="${this.T("CSV-Export")}">${this._ico("csv")}</button><button data-act="print" title="${this.T("Drucken / PDF")}" aria-label="${this.T("Drucken")}">${this._ico("print")}</button><button data-act="ori" title="${this._ori === "portrait" ? this.T("Hochformat") : this.T("Querformat")} (${this.T("zum Wechseln klicken")})" aria-label="${this.T("Seitenformat")}">${this._ico(this._ori)}</button><button data-act="rcp" title="${this.T("Belege im Druck")}: ${this._rcp ? this.T("mit") : this.T("ohne")} (${this.T("zum Wechseln klicken")})" aria-label="${this.T("Belege im Druck")}" aria-pressed="${this._rcp}">${this._ico(this._rcp ? "photo" : "photoOff")}</button><button data-act="cols" title="${this.T("Spalten")}" aria-label="${this.T("Spalten")}">${this._ico("cols")}</button><button data-act="add" title="${this.T("Eintrag von Hand hinzufügen")}" aria-label="${this.T("Eintrag von Hand")}">${this._ico("plus")}</button><span class="stat"><b>${s.count}</b><span>${this.T("Einträge")}</span></span><span class="stat"><b>${this.T({ idle: "Bereit", candidate: "Anstieg erkannt", refuelling: "Tankt" }[s.status])}</b><span>${this.T("Status")}</span></span><input type="file" id="cam" accept="image/*" capture="environment" hidden><input type="file" id="pic" accept="image/*" multiple hidden></div>
      <div class="wrap"><table class="${fixed ? "fx" : ""}" ${fixed ? `style="width:${sumW}px"` : ""}><colgroup>${order.map(c => `<col data-c="${c}" ${cw[c] || (fixed && DEFW[c]) ? `style="width:${cw[c] || DEFW[c]}px"` : ""}>`).join("")}</colgroup><thead><tr>${order.map(c => { const H = { nr: [this.T("Nr."), "n"], date: [this.T("Datum"), ""], km: [this.T("km"), "n"], station: [this.T("Tankstelle"), ""], qty: [this.T("Menge"), "n"], price: [`€/${u}`, "n"], total: [this.T("Betrag"), "n"], cons: [`${u}/100 ${this.T("km")}`, "n"], receipt: [this.T("Beleg"), ""], note: [this.T("Notiz"), ""], act: ["", ""] }[c]; return `<th data-c="${c}" class="${H[1]}${c === "act" ? "" : " sortable"}" ${sk && sk.c === c ? `aria-sort="${sk.dir > 0 ? "ascending" : "descending"}"` : ""} ${c === "act" ? "" : `draggable="true" title="${this.T("Auf eine andere Überschrift ziehen: Reihenfolge ändern")}"`}>${H[0]}${sk && sk.c === c ? `<span class="si">${sk.dir > 0 ? "▲" : "▼"}</span>` : ""}<span class="rs" data-c="${c}" title="${this.T("Ziehen: Spaltenbreite ändern · Doppelklick: Breiten und Reihenfolge zurücksetzen")}"></span></th>`; }).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="ver">Drive Energy Doc ${VERSION}</div>`;
    this._cur = v;
    this.setAttribute("dir", this._rtl ? "rtl" : "ltr");
  }

  _select(id, scroll) {   // Zeilen-Cursor: die markierte Zeile bleibt, bis eine andere gewählt wird (Klick oder Pfeiltasten)
    this._selId = id;
    this.shadowRoot.querySelectorAll("tr.rsel").forEach(x => x.classList.remove("rsel"));
    const r = [...this.shadowRoot.querySelectorAll("tbody tr[data-id]")].find(x => x.dataset.id === id);
    if (r) { r.classList.add("rsel"); if (scroll) r.scrollIntoView({ block: "nearest" }); }
  }

  _keys(ev) {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    if (this._dlg || this.shadowRoot.querySelector(".dlg, .busy") || /^(INPUT|SELECT|TEXTAREA)$/.test((ev.composedPath()[0] || {}).tagName || "")) return;
    const rows = [...this.shadowRoot.querySelectorAll("tbody tr[data-id]")];
    if (!rows.length) return;
    let i = rows.findIndex(x => x.dataset.id === this._selId);
    i = i < 0 ? (ev.key === "ArrowDown" ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + (ev.key === "ArrowDown" ? 1 : -1)));
    ev.preventDefault();
    this._select(rows[i].dataset.id, true);
  }

  async _click(ev, v) {
    const rowEl = ev.target.closest ? ev.target.closest("tr[data-id]") : null;
    if (rowEl && rowEl.closest("tbody")) this._select(rowEl.dataset.id);   // Klick setzt den Zeilen-Cursor
    const wb = ev.target.closest ? ev.target.closest("[data-wcol]") : null;
    if (wb) { this._ackDlg(v, wb.dataset.wid, wb.dataset.wcol); return; }   // Warnung antippen: Erklärung und Quittieren
    const hth = ev.target.closest ? ev.target.closest("th[data-c]") : null;
    if (hth && hth.dataset.c !== "act" && !ev.target.closest(".rs")) {
      const c = hth.dataset.c, cur = this._sort || { c: "date", dir: -1 };   // ohne Wahl gilt: Datum absteigend, neueste oben
      this._sort = { c, dir: cur.c === c ? -cur.dir : 1 };

      return this._render();
    }
    this._pvHide();
    const old = this.shadowRoot.querySelector(".pop"); if (old) old.remove();
    if (ev.target.closest && ev.target.closest(".head") && (this._data || []).length > 1) return this._vehDlg();
    const t = ev.target.closest ? (ev.target.closest("button,[data-p],[data-tab],[data-note],[data-multi]") || ev.target) : ev.target;
    if (t.dataset.multi) { this._selShow(t); return; }
    if (t.dataset.note) { this._noteShow(t, false); return; }  // Klick kann auf dem Symbol im Knopf landen
    if (t.dataset.tab != null) { this._tab = +t.dataset.tab; this._sort = null; this._selId = null; return this._render(); }
    if (t.dataset.p) {
      const lb = document.createElement("div");
      lb.className = "lb";
      lb.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;gap:10px"><img src="${t.dataset.p}" style="max-width:92vw;max-height:80vh"><div><button data-lbact="del" title="${this.T("Beleg löschen")}">${this._ico("trash")}${this.T("Beleg löschen")}</button> <button data-lbact="close" title="${this.T("Schließen")}">${this._ico("close")}${this.T("Schließen")}</button></div></div>`;
      lb.style.cssText = "position:fixed;inset:0;background:#000d;display:flex;align-items:center;justify-content:center;z-index:99";
      lb.onclick = async ev => {
        const lbb = ev.target.closest ? ev.target.closest("[data-lbact]") : null;
        const a = lbb ? lbb.dataset.lbact : undefined;
        if (a === "del") {
          if (!confirm(this.T("Dieses Foto endgültig löschen (auch das gesicherte Original)?"))) return;
          await this._hass.callWS({ type: "drive_energy_doc/delete_photo", vehicle: v.id, entry: t.dataset.entry, photo: t.dataset.name });
          lb.remove(); this._load();
        } else if (a === "close" || ev.target === lb) lb.remove();
        ev.stopPropagation();
      };
      this.shadowRoot.appendChild(lb); return;
    }
    const act = t.dataset.act;
    if (!act) return;
    if (act === "csv") { window.open(v.csv_url, "_blank"); return; }
    if (act === "add") return this._form(v, null);
    if (act === "print") return this._print(v, this._ori);
    if (act === "plate") return this._openPlate(v);
    if (act === "rcp") {
      this._rcp = !this._rcp;
      try { localStorage.setItem("deRcp", this._rcp ? "1" : "0"); } catch (e) { /* ignore */ }
      return this._render();
    }
    if (act === "ori") {
      this._ori = this._ori === "portrait" ? "landscape" : "portrait";
      try { localStorage.setItem("deOri", this._ori); } catch (e) { /* ignore */ }
      return this._render();
    }
    if (act === "cols") return this._colsDlg(v);
    if (act === "shoot") return this._pick(v, null);
    if (act === "note") return this._noteDlg(v, v.entries.find(x => x.id === t.closest("tr").dataset.id));
    if (act === "photo") return this._pick(v, v.entries.find(x => x.id === t.closest("tr").dataset.id));
    const id = t.closest("tr").dataset.id;
    const e = v.entries.find(x => x.id === id);
    if (act === "del") {
      if (confirm(this.T("Eintrag vom {0} endgültig löschen?", this._date(e.ts)))) { await this._hass.callWS({ type: "drive_energy_doc/delete", vehicle: v.id, entry: id }); this._load(); }
    } else if (act === "edit") this._form(v, e);
  }

  _vehDlg() {
    // Auswahl des Fahrzeugs: Dialog mit allen Fahrzeugen (Kennzeichen, Typ, Name)
    this._pvHide();
    const d = this._data || [];
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card">${d.map((x, i) => `<div class="vo${i === this._tab ? " on" : ""}" data-v="${i}" role="button" tabindex="0">${x.plate ? this._plate(x, true) : ""}<div><div class="tt">${this._esc(this._title(x))}</div>${x.name && this._title(x) !== x.name ? `<div class="nm">${this._esc(x.name)}</div>` : ""}</div>${this._pic(x) ? `<img class="vopic" src="${this._pic(x)}" alt="">` : ""}</div>`).join("")}<div class="df"><button data-d="cancel">${this.T("Abbrechen")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const close = () => { dlg.remove(); this._dlg = null; };
    dlg.onclick = ev => {
      ev.stopPropagation();
      const o = ev.target.closest("[data-v]");
      if (o) {
        this._tab = +o.dataset.v; this._sort = null; this._selId = null;
        try { localStorage.setItem("deVeh", d[this._tab].id); } catch (e) { /* ignore */ }
        close();
        return this._render();
      }
      if (ev.target === dlg || ev.target.closest("[data-d]")) close();
    };
    dlg.onkeydown = ev => { if (ev.key === "Escape") close(); };
  }

  _colName(c, u) {
    return { nr: this.T("Nr."), date: this.T("Datum"), km: this.T("km"), station: this.T("Tankstelle"), qty: this.T("Menge"), price: `€/${u}`, total: this.T("Betrag"), cons: `${u}/100 ${this.T("km")}`, receipt: this.T("Beleg"), note: this.T("Notiz") }[c] || c;
  }

  _colsDlg(v) {
    // Spalten ein- und ausblenden (pro Browser gemerkt); die Knöpfe ganz rechts bleiben immer
    this._pvHide();
    const u = this.T(v.unit);
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card"><div class="dh">${this.T("Spalten")}</div>${this._order().filter(c => c !== "act").map(c => `<label class="ck"><input type="checkbox" data-col="${c}" ${this._hide.includes(c) ? "" : "checked"}> ${this._esc(this._colName(c, u))}</label>`).join("")}<div class="df"><button data-d="ok" class="pri">OK</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const done = () => { dlg.remove(); this._dlg = null; this._render(); };
    dlg.onchange = ev => {
      const cb = ev.target.closest("[data-col]");
      if (!cb) return;
      this._hide = this._hide.filter(x => x !== cb.dataset.col);
      if (!cb.checked) this._hide.push(cb.dataset.col);
      try { localStorage.setItem("deHide", JSON.stringify(this._hide)); } catch (e) { /* ignore */ }
    };
    dlg.onclick = ev => { ev.stopPropagation(); if (ev.target === dlg || ev.target.closest("[data-d=ok]")) done(); };
    dlg.onkeydown = ev => { if (ev.key === "Escape" || ev.key === "Enter") done(); };
    dlg.querySelector("[data-d=ok]").focus();
  }

  _noteDlg(v, e) {
    // Notiz in einem eigenen Dialog (Textfeld), nicht über Browser-Abfragen: die funktionieren in der Handy-App oft nicht
    if (!e) return;
    this._pvHide();
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card"><div class="dh">${this.T("Notiz")} · ${this._esc(this._date(e.ts))}</div><textarea id="nt" maxlength="1000"></textarea><div class="df"><button data-d="cancel">${this.T("Abbrechen")}</button><button data-d="save" class="pri">${this.T("Speichern")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const ta = dlg.querySelector("#nt");
    ta.value = e.note || "";
    const close = () => { dlg.remove(); this._dlg = null; this._load(); };
    dlg.onclick = async ev => {
      ev.stopPropagation();
      const b = ev.target.closest("[data-d]");
      if ((b && b.dataset.d === "cancel") || ev.target === dlg) return close();
      if (b && b.dataset.d === "save") {
        try { await this._hass.callWS({ type: "drive_energy_doc/update", vehicle: v.id, entry: e.id, fields: { note: ta.value } }); }
        catch (err) { alert(this.T("Speichern fehlgeschlagen: ") + (err.message || err)); return; }
        close();
      }
    };
    dlg.onkeydown = ev => { if (ev.key === "Escape") close(); };
    ta.focus();
  }

  _pick(v, entry, ask, onFiles) {
    // Mit Eintrag = Zusatzfoto zu genau diesem Tankvorgang. Am Handy fragt ein kleiner Dialog: Kamera oder Foto aus der Galerie (Galerie); am PC gleich die Dateiauswahl.
    const go = id => {
      const input = this.shadowRoot.getElementById(id);
      input.value = "";
      input.onchange = async () => {
        const files = [...input.files];
        if (!files.length) return;
        let caption = "";
        if (entry) {
          const dt = new Date(entry.ts * 1000);
          caption = `+ ${dt.getDate()}.${dt.getMonth() + 1}.${dt.getFullYear()}`;
        }
        if (onFiles) return onFiles(files);   // z. B. Dialog „Eintrag von Hand“: nur auslesen
        await this._sendFiles(v, files, caption);
      };
      input.click();
    };
    if (!ask && !window.matchMedia("(pointer:coarse)").matches) return go("pic");   // am PC gleich die Dateiauswahl, außer im Bearbeiten-Dialog (dort immer fragen)
    this._pvHide();
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card"><button class="big" data-d="cam">${this._ico("camera")} ${this.T("Kamera")}</button><button class="big" data-d="pic">${this._ico("photo")} ${this.T("Foto aus der Galerie")}</button><div class="df"><button data-d="cancel">${this.T("Abbrechen")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const close = () => { dlg.remove(); this._dlg = null; };
    dlg.onclick = ev => {
      ev.stopPropagation();
      const b = ev.target.closest("[data-d]");
      if (b && (b.dataset.d === "cam" || b.dataset.d === "pic")) { close(); return go(b.dataset.d); }
      if (ev.target === dlg || (b && b.dataset.d === "cancel")) close();
    };
    dlg.onkeydown = ev => { if (ev.key === "Escape") close(); };
  }

  _result(v, replies, shot, awaiting, answers = []) {
    // Ergebnis des Uploads: größer und übersichtlicher als eine Browser-Meldung; bei Rückfragen mit Eingabefeld (liefert die Antwort)
    return new Promise(resolve => {
      const lines = (replies.join("\n") || this.T("Gespeichert.")).split(/\n/).map(s => s.trim()).filter(Boolean);
      const warn = lines[0].startsWith("⚠");   // Warnung statt Erfolg (z. B. KI überlastet)
      const head = lines[0].replace(/^[^\p{L}\p{N}]+/u, "") || lines[0];
      const ask = awaiting && lines.length > 2 ? lines[lines.length - 1] : "";   // lange Rückfrage unter dem Bild statt in der schmalen Spalte
      const rows = lines.slice(1, ask ? -1 : undefined).map(s => `<div>${this._esc(s)}</div>`).join("");
      const pic = this._pic(v);
      const dlg = document.createElement("div");
      dlg.className = "dlg res";
      dlg.innerHTML = `<div class="card"><div class="bd"><div class="hd"><div class="mark${awaiting ? " q" : warn ? " w" : ""}">${awaiting ? "?" : warn ? "!" : "✓"}</div><div class="ttl">${this._esc(head)}</div></div><div class="mid">${shot ? `<img class="rshot" src="${shot}" alt="">` : ""}${rows ? `<div class="rows">${rows}</div>` : ""}${pic ? `<img class="rpic" src="${pic}" alt="">` : ""}</div>${ask ? `<div class="ask">${this._esc(ask)}</div>` : ""}${awaiting && !answers.includes("yes") ? `<input id="ra" type="text" placeholder="${answers.includes("km") ? "km 61240" : this._esc(this.T("Antwort (Datum z. B. 27.10. oder „neu“):"))}" autocomplete="off">` : ""}</div><div class="df">${answers.includes("del") ? `<button data-d="del">${this.T("Löschen")}</button>` : ""}${answers.includes("doc") ? `<button data-d="doc">${this.T("Nur Dokumentation")}</button>` : ""}${answers.includes("no") ? `<button data-d="no">${this.T(answers.includes("yes") ? "Nein" : "Abbrechen")}</button>` : ""}${answers.includes("new") ? `<button data-d="new"${answers.includes("yes") ? ' class="pri"' : ""}>${this.T("Neuer Eintrag")}</button>` : ""}${answers.includes("yes") ? `<button data-d="yes"${answers.includes("new") ? "" : ' class="pri"'}>${this.T("Ja")}</button>` : `<button data-d="ok" class="pri">OK</button>`}</div></div>`;
      this.shadowRoot.appendChild(dlg);
      this._dlg = dlg;
      const inp = dlg.querySelector("#ra");
      const done = val => { dlg.remove(); this._dlg = null; resolve(val); };
      dlg.onclick = ev => { ev.stopPropagation(); if (ev.target.closest("[data-d=yes]")) done("ja"); else if (ev.target.closest("[data-d=no]")) done("nein"); else if (ev.target.closest("[data-d=new]")) done("neu"); else if (ev.target.closest("[data-d=doc]")) done("doku"); else if (ev.target.closest("[data-d=del]")) done("löschen"); else if (ev.target.closest("[data-d=ok]")) done(inp ? (answers.includes("km") && /^[\d.\s]+$/.test(inp.value.trim()) ? "km " + inp.value.trim() : inp.value.trim()) || null : null); else if (ev.target === dlg && !awaiting) done(null); };
      dlg.onkeydown = ev => { if (ev.key === "Enter" && inp) dlg.querySelector("[data-d=ok]").click(); if (ev.key === "Escape") done(null); };
      if (inp) inp.focus(); else (dlg.querySelector("button.pri") || dlg.querySelector("button")).focus();
    });
  }

  async _upload(v, file, text, mode, signal) {
    const fd = new FormData();
    if (file) fd.append("file", file, file.name || "beleg.jpg");
    fd.append("text", text || "");
    if (mode === "batch") fd.append("batch", "1");     // Stapel: Plausibilitätsprüfung erst am Ende
    if (mode === "finish") fd.append("finish", "1");
    if (mode === "scan" || mode === "keep") fd.append("scan", "1");       // nur auslesen, keinen Eintrag anlegen
    if (mode === "keep") fd.append("keep", "1");       // ... und nicht mit der KI lesen, nur Foto ablegen
    const r = await this._hass.fetchWithAuth(`/api/drive_energy_doc/upload/${v.id}`, { method: "POST", body: fd, signal });
    if (!r.ok) throw new Error(`${this.T("Fehler")} ${r.status}`);
    return r.json();
  }

  _send(v, file, text) { return this._sendFiles(v, file ? [file] : [], text); }

  async _taken(f) {
    // Aufnahmezeit (EXIF DateTimeOriginal) aus dem Kopf einer JPEG-Datei, in ms; null wenn nicht vorhanden. Dateinamen sagen nichts: Kameras vergeben sie beliebig.
    try {
      const b = new DataView(await f.slice(0, 131072).arrayBuffer());
      if (b.getUint16(0) !== 0xFFD8) return null;
      let o = 2;
      while (o + 4 < b.byteLength) {
        const m = b.getUint16(o), len = b.getUint16(o + 2);
        if (m === 0xFFE1 && b.getUint32(o + 4) === 0x45786966) {
          const t0 = o + 10, le = b.getUint16(t0) === 0x4949;
          const g16 = p => b.getUint16(t0 + p, le), g32 = p => b.getUint32(t0 + p, le);
          const find = (p, want) => { const n = g16(p); for (let i = 0; i < n; i++) { const e = p + 2 + i * 12; if (g16(e) === want) return e; } return null; };
          const ex = find(g32(4), 0x8769); if (ex == null) return null;
          const e2 = find(g32(ex + 8), 0x9003); if (e2 == null) return null;
          const off = g32(e2 + 8), n2 = g32(e2 + 4);
          let s = ""; for (let i = 0; i < n2 - 1; i++) s += String.fromCharCode(b.getUint8(t0 + off + i));
          const r = s.match(/^(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)/);
          return r ? new Date(+r[1], r[2] - 1, +r[3], +r[4], +r[5], +r[6]).getTime() : null;
        }
        if ((m & 0xFF00) !== 0xFF00) break;
        o += 2 + len;
      }
    } catch (e) { /* kein EXIF */ }
    return null;
  }

  async _sendFiles(v, files, text) {
    if (files.length > 1) {   // chronologisch nach Aufnahmezeit (sonst nach Änderungsdatum der Datei), nicht nach Dateiname; bei Gleichstand bleibt die Reihenfolge
      const keyed = await Promise.all(files.map(async (f, i) => ({ f, i, k: (await this._taken(f)) ?? f.lastModified ?? 0 })));
      keyed.sort((a, b) => a.k - b.k || a.i - b.i);
      files = keyed.map(x => x.f);
    }
    // Ein oder mehrere Fotos nacheinander hochladen (in der gewählten Reihenfolge). Rückfragen des Bots werden sofort gestellt;
    // bei mehreren Fotos folgt am Ende eine Übersicht.
    const total = Math.max(files.length, 1), results = [], urls = [];
    let cancelled = false;
    const ctl = new AbortController();
    const pic = this._pic(v);
    const busy = document.createElement("div");
    busy.className = "busy";
    this.shadowRoot.appendChild(busy);
    busy.onclick = ev => { if (ev.target.closest("[data-d=stop]")) { cancelled = true; ctl.abort(); } };   // Abbruch: nichts weiter senden
    const shots = files.map(f => { const u = URL.createObjectURL(f); urls.push(u); return u; });
    const strip = i => total > 1 ? `<div class="pstrip">${shots.map((u, k) => `<div class="pt${k < i ? " done" : k === i ? " cur" : ""}"><img src="${u}" alt="">${k < i ? "<b>✓</b>" : ""}</div>`).join("")}</div><div class="pbar"><i style="width:${Math.round(i / total * 100)}%"></i></div>` : "";
    const paint = (shot, i) => {
      busy.innerHTML = `<div class="card">${pic ? `<img class="bpic" src="${pic}" alt="">` : ""}${v.plate ? `<div class="bplate">${this._plate(v)}</div>` : ""}${shot ? `<div class="scan"><img src="${shot}" alt=""><svg class="lupe" viewBox="0 0 64 64" aria-hidden="true"><circle cx="26" cy="26" r="19" fill="rgba(255,255,255,.28)" stroke="#1b1b1b" stroke-width="5"/><path d="M40 40 L58 58" stroke="#1b1b1b" stroke-width="8" stroke-linecap="round"/><path d="M15 20 A13 13 0 0 1 24 12" stroke="rgba(255,255,255,.9)" stroke-width="3" fill="none" stroke-linecap="round"/></svg></div>` : ""}<div class="brow"><div class="spin"></div><div>${this.T("Beleg wird gelesen …")}${total > 1 ? ` (${i + 1} / ${total})` : ""}</div></div>${strip(i)}<button class="stopb" data-d="stop">${this.T("Abbrechen")}</button></div>`;
    };
    try {
      for (let i = 0; i < total; i++) {
        const file = files[i] || null;
        const shot = shots[i] || "";
        paint(shot, i);
        if (cancelled) break;
        let j = await this._upload(v, file, file ? text : text, total > 1 ? "batch" : "", ctl.signal);
        for (let guard = 0; j.awaiting && guard < 3; guard++) {   // Rückfrage des Bots: Antwort abfragen und weiter
          busy.style.display = "none";
          if (total === 1 && file && (j.answers || []).includes("doc")) {   // keine Tankquittung lesbar: Foto übergeben, Dialog „Eintrag von Hand“ mit dem Foto öffnen
            let pre = null;
            try {
              await this._upload(v, null, "löschen", "", ctl.signal);
              pre = (await this._upload(v, file, "", "keep", ctl.signal)).scan;
            } catch (err) { /* dann eben die normale Rückfrage */ }
            if (pre && pre.photo) { pre.hint = (j.replies || []).join(" "); busy.remove(); this._load(); return this._form(v, null, pre); }
          }
          const ans = await this._result(v, j.replies || [], shot, true, j.answers || []);
          busy.style.display = "";
          if (!ans) { j = { replies: j.replies, awaiting: false }; break; }
          paint(shot, i);
          j = await this._upload(v, null, ans, total > 1 ? "batch" : "", ctl.signal);
        }
        if (total === 1) {   // einzelnes Foto: Ergebnis sofort groß zeigen
          busy.style.display = "none";
          await this._result(v, j.replies || [], shot, false);
          if (j.entry) { this._jumpId = j.entry; busy.remove(); await this._load(); return; }   // direkt in die Liste, die Zeile des Belegs ist markiert und im Blick
        } else results.push({ shot, replies: j.replies || [] });
      }
      if (cancelled) { this._upload(v, null, "", "finish").catch(() => {}); }   // Stapel auf dem Server abschließen, keine Übersicht
      else if (total > 1) {
        let warns = [];
        try { warns = (await this._upload(v, null, "", "finish")).replies || []; } catch (e) { /* Prüfung am Ende ist optional */ }
        busy.style.display = "none";
        await this._summary(v, results, warns);
      }
    } catch (e) {
      if (cancelled || (e && e.name === "AbortError")) this._upload(v, null, "", "finish").catch(() => {});
      else alert(this.T("Upload fehlgeschlagen: ") + (e.message || e));
    }
    finally { busy.remove(); urls.forEach(u => URL.revokeObjectURL(u)); }
    this._load();
  }

  _summary(v, results, warns = []) {
    // Übersicht nach mehreren Fotos: je Foto Vorschaubild und Ergebnis
    return new Promise(resolve => {
      const items = results.map(r => {
        const lines = (r.replies.join("\n") || this.T("Gespeichert.")).split(/\n/).map(s => s.trim()).filter(Boolean);
        const head = lines[0].replace(/^[^\p{L}\p{N}]+/u, "") || lines[0];
        return `<div class="sm">${r.shot ? `<img src="${r.shot}" alt="">` : ""}<div><b>${this._esc(head)}</b><div class="smr">${this._esc(lines.slice(1).join(" · "))}</div></div></div>`;
      }).join("");
      const dlg = document.createElement("div");
      dlg.className = "dlg res";
      dlg.innerHTML = `<div class="card"><div class="hd"><div class="mark">✓</div><div class="ttl">${this.T("{0} Fotos verarbeitet", results.length)}</div></div><div class="smlist">${items}</div>${warns.length ? `<div class="smwarn">${warns.map(w => `<div>${this._esc(w)}</div>`).join("")}</div>` : ""}<div class="df"><button data-d="ok" class="pri">OK</button></div></div>`;
      this.shadowRoot.appendChild(dlg);
      this._dlg = dlg;
      const done = () => { dlg.remove(); this._dlg = null; resolve(); };
      dlg.onclick = ev => { ev.stopPropagation(); if (ev.target === dlg || ev.target.closest("[data-d=ok]")) done(); };
      dlg.onkeydown = ev => { if (ev.key === "Escape" || ev.key === "Enter") done(); };
      dlg.querySelector("button").focus();
    });
  }

  _print(v, orient = this._ori) {
    // A4 quer oder hoch; im Druckdialog "Als PDF speichern" wählen. Alle Einträge, darunter die Belegfotos je Eintrag (max. 4).
    const u = this.T(v.unit), e = this._esc.bind(this);
    const pn = {}; [...v.entries].filter(x => x.kind !== "extra").sort((p, q) => p.ts - q.ts).forEach((x, i) => { pn[x.id] = i + 1; });
    const rows = [...v.entries].reverse().map(x => `<tr><td class="n">${pn[x.id] || ""}</td><td>${this._date(x.ts)}</td><td class="n">${x.odometer != null ? this._fmt(x.odometer, 0) : ""}</td><td>${x.kind === "extra" ? "[" + e(x.item || this.T("Zubehör")) + "] " : ""}${e(x.station || "")}<br><small>${e(x.address || "")}</small><br><small>${this._gps(x, false)}</small></td><td class="n">${x.quantity != null ? this._fmt(x.quantity) + " " + (x.kind === "extra" ? e(x.unit || "") : (v.phev && x.energy === "electric" ? "kWh" : u)) : ""}</td><td class="n">${this._fmt(x.unit_price, 3)}</td><td class="n">${this._fmt(x.total)} €</td><td class="n">${x.consumption != null ? this._fmt(x.consumption) : ""}</td><td>${e(x.note || "")}</td></tr>`).join("");
    const photos = v.entries.filter(x => (x.photo_urls || []).length).map(x => `<div class="g"><div class="c">${this._date(x.ts)} · ${e(x.station || "")} · ${this._fmt(x.total)} €</div>${x.photo_urls.slice(0, 4).map(p => `<img src="${new URL(p, location.origin).href}">`).join("")}</div>`).join("");
    const total = v.entries.reduce((a, x) => a + (x.total || 0), 0), qty = v.entries.reduce((a, x) => a + (x.quantity || 0), 0);
    const html = `<!doctype html><meta charset="utf-8"><title>Drive Energy Doc ${e(v.name)}${v.plate ? " " + e(v.plate) : ""}</title><style>
      @page{size:A4 ${orient};margin:${orient === "portrait" ? "10mm" : "12mm"}}body{font:${orient === "portrait" ? "9.5px" : "11px"}/1.35 Arial,sans-serif;color:#000}h1{font-size:16px;margin:0 0 4px}
      table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #bbb;padding:3px 5px;text-align:left;vertical-align:top}
      th{border-bottom:2px solid #000}.n{text-align:right;white-space:nowrap}small{color:#555}
      .g{break-inside:avoid;margin-top:10px}.c{font-weight:bold;margin-bottom:3px}.g img{max-height:75mm;max-width:90mm;margin-right:6px;border:1px solid #ccc}
      h2{margin:14px 0 0;font-size:13px;break-before:page}</style>
      <h1>Drive Energy Doc ${e(v.name)}${v.plate ? " · " + e(v.plate) : ""}</h1><div>${v.entries.length} ${this.T("Einträge")} · ${this._fmt(qty)} ${u} · ${this._fmt(total)} € · ${this.T("erstellt")} ${new Date().toLocaleDateString(this._locale || "de-DE")}</div>
      <table><thead><tr><th class="n">${this.T("Nr.")}</th><th>${this.T("Datum")}</th><th class="n">${this.T("km")}</th><th>${this.T("Tankstelle")}</th><th class="n">${this.T("Menge")}</th><th class="n">€/${u}</th><th class="n">${this.T("Betrag")}</th><th class="n">${u}/100 ${this.T("km")}</th><th>${this.T("Notiz")}</th></tr></thead><tbody>${rows}</tbody></table>
      ${photos && this._rcp ? `<h2>${this.T("Belege")}</h2>${photos}` : ""}`;
    if (this._printOnlyHtml) return html;  // Testhilfe
    const f = document.createElement("iframe");
    f.style.cssText = "position:fixed;width:0;height:0;border:0";
    this.shadowRoot.appendChild(f);
    f.srcdoc = html;
    f.onload = () => {
      const imgs = [...f.contentDocument.images];
      Promise.all(imgs.map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; }))).then(() => {
        f.contentWindow.focus(); f.contentWindow.print(); setTimeout(() => f.remove(), 60000);
      });
    };
  }

  _form(v, e, pre) {   // pre: Ergebnis von scan_photo (Foto schon abgelegt), z. B. wenn der Beleg nicht lesbar war
    // Korrigieren / von Hand anlegen: ein Dialog mit allen Feldern (statt einer Kette von Browser-Abfragen)
    this._pvHide();
    const esc = x => this._esc(x == null ? "" : String(x));
    const pad = n => String(n).padStart(2, "0");
    const local = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const whenOrig = local(e ? new Date(e.ts * 1000) : new Date());
    const isExtra = e ? e.kind === "extra" : true;   // neuer Eintrag von Hand: Vorgabe Zubehör / Sonstiges, nicht Kraftstoff
    // Verbrauchsmaterial: Auswahl mit Vorgaben (füllt Bezeichnung und Einheit), „Sonstiges“ = frei eintippen
    const PRESETS = [{ k: "AdBlue", unit: "l", m: ["adblue"] }, { k: "Öl", unit: "l", m: ["öl", "oel", "oil"] }, { k: "Scheibenreiniger", unit: "l", m: ["scheibenreiniger", "scheibenwasser", "washer"] }, { k: "Waschen", unit: "", m: ["wasch", "wäsch", "wash"] }];
    const itemLow = (e && e.item ? String(e.item) : "").toLowerCase();
    const subSel = isExtra ? (PRESETS.find(x => [this.T(x.k).toLowerCase(), x.k.toLowerCase(), ...x.m].some(w => itemLow === w || itemLow.endsWith(w) || (w.length >= 5 && itemLow.includes(w)))) || {}).k || "other" : "other";
    const fld = (id, label, val, extra = "") => `<label class="fl"${extra}><span>${label}</span><input id="${id}" type="text" inputmode="${id === "f_date" || id === "f_item" || id === "f_unit" ? "text" : "decimal"}" value="${esc(val)}" autocomplete="off"></label>`;
    const curSel = !!(e && e.orig && (e.orig.unknown || e.orig.assumed || e.orig.manual));   // nur wenn die Währung nicht erkannt wurde (unbekannt, aus dem Land angenommen oder schon von Hand gesetzt)
    const gradeOpts = v.energy === "diesel" ? ["diesel", "diesel_premium"] : v.energy === "lpg" ? ["lpg", "e10", "e5", "ron95", "ron98"] : ["e10", "e5", "ron95", "ron98", "lpg"];   // Sorten, die zum Fahrzeug passen
    const gradeCur = e && e.fuel && gradeOpts.includes(e.fuel) ? e.fuel : (gradeOpts.includes(v.energy) ? v.energy : gradeOpts[0]);
    const dlg = document.createElement("div");
    dlg.className = "dlg form";
    dlg.innerHTML = `<div class="card"><div class="bd">
      <div class="dh">${this.T(e ? "Bearbeiten" : "Eintrag von Hand")}${e ? " · " + esc(this._date(e.ts)) : ""}</div>
            <label class="fl"><span>${this.T("Datum")}</span><input id="f_when" type="datetime-local" value="${whenOrig}"></label>
      <div class="g2"><label class="fl"><span>${this.T("Art")}</span><select id="f_kind"><option value="fuel">${esc(v.energy === "electric" ? this.T("Strom") : this.T("Kraftstoff"))}</option>${v.phev ? `<option value="electric"${e && e.kind !== "extra" && e.energy === "electric" ? " selected" : ""}>${esc(this.T("Strom"))}</option>` : ""}${PRESETS.map(x => `<option value="${x.k}"${isExtra && subSel === x.k ? " selected" : ""}>${esc(this.T(x.k))}</option>`).join("")}<option value="other"${isExtra && subSel === "other" ? " selected" : ""}>${esc(this.T("Sonstiges"))}</option></select></label>
      <label class="fl" id="w_grade"${isExtra || v.energy === "electric" || (e && e.energy === "electric") ? ' style="display:none"' : ""}><span>${this.T("Kraftstoffart")}</span><select id="f_grade">${gradeOpts.map(k => `<option value="${k}"${k === gradeCur ? " selected" : ""}>${esc(FUEL_GRADES[k])}</option>`).join("")}</select></label></div>
      <div class="g2">${fld("f_item", this.T("Bezeichnung"), e ? e.item || "" : "", ` id="w_item"${isExtra ? "" : ' style="display:none"'}`)}
      ${fld("f_unit", this.T("Einheit (z. B. l, Stk), leer = keine"), e ? e.unit : "", ` id="w_unit"${isExtra ? "" : ' style="display:none"'}`)}</div>
      <div class="g2">
        ${fld("f_q", this.T("Menge"), e ? e.quantity : "")}
        ${curSel ? `<label class="fl"><span>${this.T("Preis")} €</span><div class="pr"><input id="f_p" type="text" inputmode="decimal" value="${esc(e.unit_price)}" autocomplete="off" style="min-width:0"><select id="f_cur" title="${esc(this.T("Währung des Belegs"))}" aria-label="${esc(this.T("Währung des Belegs"))}">${e.orig.currency ? "" : '<option value="" selected>?</option>'}${["EUR", ...CURRENCIES].map(c => `<option value="${c}"${c === e.orig.currency ? " selected" : ""}>${c}</option>`).join("")}</select></div></label>` : fld("f_p", this.T("Preis") + " €", e ? e.unit_price : "")}
        ${fld("f_t", this.T("Betrag") + " €", e ? e.total : "")}
        ${fld("f_km", this.T("Kilometerstand"), e ? e.odometer : "")}
      </div>
      <label class="fl"><span>${this.T("Notiz")}</span><textarea id="f_note" maxlength="1000">${esc(e ? e.note : "")}</textarea></label>
      <div id="f_ph" class="phn" style="display:none"></div>
    </div><div class="df"><button data-d="photo" class="ico" title="${this.T("Foto zu diesem Eintrag")}" aria-label="${this.T("Foto hinzufügen")}">${this._ico("camera")}</button><button data-d="cancel">${this.T("Abbrechen")}</button><button data-d="save" class="pri">${this.T("Speichern")}</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const $ = id => dlg.querySelector("#" + id);
    // Handy: die Bildschirmtastatur verkleinert nur den sichtbaren Bereich; der Dialog passt sich ihm an, damit nichts verdeckt wird
    const vv = window.visualViewport;
    const fit = () => { if (vv) { dlg.style.inset = "auto 0 auto 0"; dlg.style.top = vv.offsetTop + "px"; dlg.style.height = vv.height + "px"; dlg.querySelector(".card").style.maxHeight = Math.max(240, vv.height - 16) + "px"; } };
    const coarse = window.matchMedia("(pointer:coarse)").matches;
    if (vv && coarse) { vv.addEventListener("resize", fit); vv.addEventListener("scroll", fit); fit(); }
    const photos = [];   // per Scan abgelegte Fotos, noch keinem Eintrag zugeordnet
    const ph = txt => { const n = $("f_ph"); n.textContent = txt || ""; n.style.display = txt ? "" : "none"; };
    const discard = async names => { for (const n of names) { try { await this._hass.callWS({ type: "drive_energy_doc/discard_photo", vehicle: v.id, photo: n }); } catch (err) { /* egal */ } } };
    const ask = (msg, yes, no) => new Promise(res => {   // kleine Rückfrage über dem Dialog
      const q = document.createElement("div");
      q.className = "dlg";
      q.style.zIndex = 110;
      q.innerHTML = `<div class="card"><div class="dh">${esc(msg)}</div><div class="df"><button data-q="no">${esc(no)}</button><button data-q="yes" class="pri">${esc(yes)}</button></div></div>`;
      this.shadowRoot.appendChild(q);
      q.onclick = ev => { ev.stopPropagation(); const b = ev.target.closest("[data-q]"); if (b) { q.remove(); res(b.dataset.q === "yes"); } };
    });
    const scan = async files => {   // Foto per KI lesen und die gefundenen Werte in diesen Dialog eintragen (der Dialog bleibt offen)
      const btn = dlg.querySelector('[data-d="photo"]');
      btn.disabled = true;
      ph(this.T("Foto wird gelesen …"));
      const busy = document.createElement("div");   // Fortschritt mitten über dem Dialog (die Zeile im Dialog liegt am Handy oft außerhalb des sichtbaren Bereichs)
      busy.className = "dlg";
      busy.style.zIndex = 120;
      busy.innerHTML = `<div class="card" style="align-items:center;text-align:center;gap:14px;padding:26px 30px;max-width:300px"><div class="spin"></div><div class="dh">${esc(this.T("Foto wird gelesen …"))}</div></div>`;
      this.shadowRoot.appendChild(busy);
      let r = null;
      try { r = (await this._upload(v, files[0], "", "scan")).scan; } catch (err) { busy.remove(); ph(""); btn.disabled = false; alert(this.T("Fehler") + ": " + (err.message || err)); return; }
      busy.remove();
      btn.disabled = false;
      if (!r) { ph(""); return; }
      if (r.busy) { ph(""); alert(this.T("Die KI ist gerade überlastet. Bitte in ein paar Minuten noch einmal versuchen.")); return; }
      if (!r.found) {
        ph("");
        const keep = await ask(this.T("Auf dem Foto konnte ich keine Daten lesen. Soll es trotzdem zur Dokumentation behalten werden?"), this.T("Behalten"), this.T("Verwerfen"));
        if (!keep) return discard([r.photo]);
        photos.push(r.photo);
        if (!$("f_item").value.trim()) $("f_item").value = this.T("Dokumentation");
        ph(this.T("{0} Foto(s) angehängt", photos.length));
        return;
      }
      photos.push(r.photo);
      const set = (id, x) => { if (x != null && x !== "") $(id).value = x; };
      const cat = { adblue: "AdBlue", oil: "Öl", washer: "Scheibenreiniger", carwash: "Waschen" }[r.category];   // Kategorie aus dem Beleg wählen
      if (cat || r.category === "other") {
        $("f_kind").value = cat || "other"; $("f_kind").onchange();
        if (!cat && r.item) $("f_item").value = r.item;
      } else if (r.receipt || r.quantity || r.total) { $("f_kind").value = v.phev && r.category === "charging" ? "electric" : "fuel"; $("f_kind").onchange(); }
      if (r.fuel_grade && gradeOpts.includes(r.fuel_grade)) $("f_grade").value = r.fuel_grade;
      set("f_q", r.quantity); set("f_p", r.unit_price); set("f_t", r.total); set("f_km", r.odometer ? Math.round(r.odometer) : null);
      if (r.note) $("f_note").value = $("f_note").value.trim() ? $("f_note").value.trim() + " · " + r.note : r.note;   // Fremdwährung: Originalpreis und Kurs
      if (r.ts && !e) { const d = new Date(r.ts * 1000); if (!isNaN(d)) $("f_when").value = local(d); }
      ph(this.T("Foto gelesen: Werte eingetragen, bitte prüfen.") + (photos.length > 1 ? " · " + this.T("{0} Foto(s) angehängt", photos.length) : ""));
    };
    const close = () => { if (photos.length) { discard(photos); photos.length = 0; } if (vv && coarse) { vv.removeEventListener("resize", fit); vv.removeEventListener("scroll", fit); } dlg.remove(); this._dlg = null; this._load(); };
    const num = s => (s == null || String(s).trim() === "" ? null : parseFloat(String(s).replace(",", ".")));
    const preset = k => { const m = PRESETS.find(x => x.k === k); if (m) { $("f_item").value = this.T(m.k); $("f_unit").value = m.unit; } };
    $("f_kind").onchange = () => {   // alles außer Kraftstoff/Strom ist Zubehör: Bezeichnung und Einheit, bei den Vorgaben automatisch gefüllt
      const k = $("f_kind").value, x = k !== "fuel" && k !== "electric";
      ["w_item", "w_unit"].forEach(id => { dlg.querySelector("#" + id).style.display = x ? "" : "none"; });
      dlg.querySelector("#w_grade").style.display = x || k === "electric" ? "none" : "";
      if (PRESETS.some(m => m.k === k)) preset(k);
    };
    const save = async () => {
      const f = { quantity: num($("f_q").value), unit_price: num($("f_p").value), total: num($("f_t").value), odometer: num(/^\d{1,3}(\.\d{3})+$/.test($("f_km").value.trim()) ? $("f_km").value.trim().replace(/\./g, "") : $("f_km").value), note: $("f_note").value };
      const extra = $("f_kind").value !== "fuel" && $("f_kind").value !== "electric";
      f.kind = extra ? "extra" : "fuel";
      f.fuel = !extra && $("f_kind").value !== "electric" && v.energy !== "electric" ? $("f_grade").value : "";
      if (v.phev && !extra) f.energy = $("f_kind").value === "electric" ? "electric" : "fuel";   // auch nachträglich umstellbar (z. B. ein Ölbon, der als Tanken gelesen wurde)
      if (extra) { f.item = ($("f_item").value || "").trim() || this.T("Zubehör"); f.unit = ($("f_unit").value || "").trim(); }
      if (e && $("f_when").value && $("f_when").value !== whenOrig) { const w = new Date($("f_when").value); if (!isNaN(w)) f.ts = w.getTime() / 1000; }
      try {
        if (e) {
          if (photos.length) f.photos = [...photos];   // im Dialog aufgenommene Fotos gehören jetzt zum Eintrag
          await this._hass.callWS({ type: "drive_energy_doc/update", vehicle: v.id, entry: e.id, fields: f });
          photos.length = 0;
        } else {
          const w = new Date($("f_when").value);
          if (isNaN(w)) { $("f_when").focus(); return; }
          f.ts = w.getTime() / 1000;
          if (photos.length) f.photos = [...photos];
          await this._hass.callWS({ type: "drive_energy_doc/add", vehicle: v.id, fields: f });
          photos.length = 0;   // gehören jetzt zum Eintrag
        }
      } catch (err) { alert(this.T("Speichern fehlgeschlagen: ") + (err.message || err)); return; }
      close();
      this._load();
    };
    dlg.onchange = ev => {   // Währung gewählt: Betrag und Preis werden neu umgerechnet, der Dialog öffnet danach mit den neuen Werten
      if (ev.target.id !== "f_cur" || !e || !ev.target.value) return;
      ev.target.disabled = true;
      this._hass.callWS({ type: "drive_energy_doc/set_currency", vehicle: v.id, entry: e.id, currency: ev.target.value }).then(async () => {
        close();
        await this._load();
        const v2 = (this._data || []).find(x => x.id === v.id), e2 = v2 && v2.entries.find(x => x.id === e.id);
        if (e2) this._form(v2, e2);
      }, err => { ev.target.disabled = false; alert(this.T("Fehler") + ": " + (err.message || err)); });
    };
    dlg.onclick = ev => {
      ev.stopPropagation();
      const b = ev.target.closest("[data-d]");
      if ((b && b.dataset.d === "cancel") || ev.target === dlg) return close();
      if (b && b.dataset.d === "save") save();
      if (b && b.dataset.d === "photo") this._pick(v, null, true, scan);   // auch beim Bearbeiten: das Foto wird gelesen, die Werte kommen in den offenen Dialog, gespeichert wird erst mit „Speichern“
    };
    dlg.onkeydown = ev => { if (ev.key === "Escape") close(); else if (ev.key === "Enter" && ev.target.tagName === "INPUT") save(); };
    if (pre && pre.photo) {   // unlesbarer Beleg aus dem Hauptmenü: Foto hängt schon am Dialog, Rest von Hand
      photos.push(pre.photo);
      if (!$("f_item").value.trim()) $("f_item").value = this.T("Dokumentation");
      if (pre.ts) { const d = new Date(pre.ts * 1000); if (!isNaN(d)) $("f_when").value = local(d); }
      ph(pre.hint || (this.T("Auf dem Foto konnte ich keine Daten lesen. Soll es trotzdem zur Dokumentation behalten werden?").split(".")[0] + ". " + this.T("{0} Foto(s) angehängt", photos.length)));
    }
    if (!coarse) (e ? $("f_q") : $("f_kind")).focus();   // am Handy nicht: sonst springt gleich die Tastatur auf
  }
}
if (!customElements.get("drive-energy-doc-panel")) customElements.define("drive-energy-doc-panel", DriveEnergyDocPanel);
