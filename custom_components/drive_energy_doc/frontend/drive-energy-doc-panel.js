/* Drive-Energy-Doc-Panel: Fahrzeug-Reiter, Tankliste mit Belegfotos, Bearbeiten, CSV-Export */
const DEFW = { nr: 46, sol: 48, loss: 56 };   // Standardbreite einzelner Spalten in px (sonst 120 bei fester Breite)
const CURRENCIES = ["ALL", "AED", "AUD", "BAM", "BRL", "BYN", "CAD", "CHF", "CNY", "CZK", "DKK", "EGP", "GBP", "GEL", "HUF", "INR", "ISK", "JPY", "MAD", "MDL", "MKD", "MXN", "NOK", "NZD", "PLN", "RON", "RSD", "SEK", "THB", "TND", "TRY", "UAH", "USD", "ZAR"];
const FUEL_GRADES = { diesel: "Diesel", diesel_premium: "Diesel Premium", e10: "Super E10", e5: "Super E5", ron95: "Super 95", ron98: "Super 98", lpg: "LPG" };
const COLS = ["nr", "date", "start", "end", "lfrom", "lto", "km", "station", "qty", "ctype", "kcar", "kwb", "pavg", "ppk", "price", "total", "cons", "sol", "loss", "receipt", "note", "act"];
const DEF_HIDE = ["start", "end", "lfrom", "lto", "ctype", "kcar", "kwb", "pavg", "ppk"];   // Laden von / bis: vorhanden, aber zunächst ausgeblendet

const VERSION = "0.1.87b3";

class DriveEnergyDocPanel extends HTMLElement {
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._loadLang().then(() => this._load(), () => this._load());
    if (h && h.connection && this._conn !== h.connection) {   // nach einem HA-Neustart (Verbindung wieder da): alles neu laden
      this._conn = h.connection;
      h.connection.addEventListener("ready", () => { this._sig = null; this._load(); });
    }
    this._subscribe();
    if (this._mb) this._menu();
  }

  // Menü-Button (Seitenleiste) für schmale Bildschirme, z. B. Companion-App am Handy: dort ist die Seitenleiste eingeklappt und nur über diesen Button erreichbar.
  // HAs eigenes ha-menu-button blendet sich selbst aus, wenn die Seitenleiste sichtbar ist; fehlt es, ein einfacher Ersatz, der dasselbe Ereignis auslöst.
  _menu() {
    const root = this.shadowRoot;
    if (!root) return;
    if (!this._mb) {
      if (customElements.get("ha-menu-button")) {
        this._mb = document.createElement("ha-menu-button");
      } else {
        this._mb = document.createElement("button");
        this._mb.className = "mbtn";
        this._mb.setAttribute("aria-label", "Menu");
        this._mb.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg>';
        this._mb.addEventListener("click", () => this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })));
      }
      this._mb.classList.add("menu");
    }
    this._mb.hass = this._hass;
    this._mb.narrow = !!this._narrow;
    this._mb.style.display = this._narrow || (this._hass && this._hass.dockedSidebar === "always_hidden") ? "" : "none";   // wie HA: schmal oder Seitenleiste ganz ausgeblendet
    const head = root.querySelector(".head");
    if (this._mb.parentNode === (head || root)) return;   // hass kommt sehr oft: nur nach einem neuen Aufbau einhängen
    if (head) head.insertBefore(this._mb, head.firstChild);
    else root.insertBefore(this._mb, (root.querySelector("style") || {}).nextSibling || root.firstChild);
  }

  _subscribe() {
    // Live-Ereignisse vom Server: ein Foto aus Telegram/WhatsApp wird verarbeitet (Hinweis), die Antwort kommt (Meldung), die Liste wird neu geladen
    if (this._sub || this._subBusy || !this._hass || !this._hass.connection || !this.isConnected) return;
    this._subBusy = true;
    this._hass.connection.subscribeMessage(ev => this._onEvent(ev), { type: "drive_energy_doc/subscribe" }).then(u => { this._sub = u; this._subBusy = false; }, () => { this._subBusy = false; });
  }

  _liveRowHtml(lv, v, u, order) {
    const q = lv.wb_kwh != null ? lv.wb_kwh : lv.est_quantity, kwu = v.phev ? "kWh" : u;
      const cell = {
        nr: `<td class="n nr"><span class="pulse"></span></td>`,
        date: `<td><span>${this._d(lv.ts_start)}</span><span class="tm">${this._tm(lv.ts_start)}</span></td>`,
        km: `<td class="n">${lv.odometer != null ? this._fmt(lv.odometer, 0) : "–"}</td>`,
        price: `<td class="n">${lv.unit_price != null ? this._fmt(lv.unit_price, 3) : ""}</td>`,
        total: `<td class="n">${lv.total != null ? this._fmt(lv.total) + " €" : ""}</td>`,
        station: `<td><div>${this._esc(this.T("Lädt gerade"))}</div>${lv.kw ? `<div class="src">${this._fmt(lv.kw, 1)} kW</div>` : lv.paused ? `<div class="src">${this._esc(this.T("pausiert"))}</div>` : ""}</td>`,
        qty: `<td class="n">${q != null ? this._fmt(q) + " " + kwu : "–"}<div class="src">${lv.level_from != null ? Math.round(lv.level_from) + "→" + Math.round(lv.level_to) + " % " : lv.level_to != null ? Math.round(lv.level_to) + " % " : ""}${lv.wb_kwh != null ? "" : this._esc(this.T("berechnet")) + " "}${lv.charge_type ? `<span class="ct ${lv.charge_type}">${lv.charge_type.toUpperCase()}</span>` : ""}</div></td>`,
        ctype: `<td class="ctr">${lv.charge_type ? `<span class="ct ${lv.charge_type}">${lv.charge_type.toUpperCase()}</span>` : ""}</td>`,
        start: `<td>${this._tm(lv.ts_start)}</td>`,
        kcar: `<td class="n">${lv.est_quantity != null ? this._fmt(lv.est_quantity) + " kWh" : ""}</td>`,
        pavg: `<td class="n">${lv.avg_kw ? this._fmt(lv.avg_kw, 1) + " kW" : ""}</td>`,
        ppk: `<td class="n">${lv.kw ? this._fmt(lv.kw, 1) + " kW" : ""}</td>`,
        kwb: `<td class="n">${lv.wb_kwh != null ? this._fmt(lv.wb_kwh) + " kWh" : ""}</td>`,
        lfrom: `<td class="n">${lv.level_from != null ? Math.round(lv.level_from) + " %" : ""}</td>`,
        lto: `<td class="n">${lv.level_to != null ? Math.round(lv.level_to) + " %" : ""}</td>`,
        loss: `<td class="n">${lv.loss_pct != null ? (lv.loss_prov ? `<span class="src" title="${this._esc(this.T("Vorläufig: Wallbox-Energie bis zur letzten Meldung des Ladestands"))}">≈ ${lv.loss_pct} %</span>` : (lv.loss_pct < 0 ? `<span class="est">${lv.loss_pct} %</span>` : lv.loss_pct + " %")) : ""}</td>`,
        note: `<td>${lv.est_quantity != null || lv.wb_kwh != null ? `${lv.est_quantity != null ? `<div class="src">${this._esc(this.T("Akku"))} ${this._fmt(lv.est_quantity)} kWh</div>` : ""}${lv.wb_kwh != null ? `<div class="src">Wallbox ${this._fmt(lv.wb_kwh)} kWh</div>` : ""}` : ""}</td>`,
      };
    cell.act = `<td><button data-act="curve" title="${this.T("Ladekurve")}" aria-label="${this.T("Ladekurve")}">${this._ico("chart")}</button>${lv.provisional ? "" : ` <button data-act="finish" title="${this.T("Ladung jetzt abschließen")}" aria-label="${this.T("Ladung jetzt abschließen")}">${this._ico("check")}</button>`}</td>`;   // Kurve der laufenden Ladung
    return `<tr class="c-live" data-id="live">${order.map(k => (cell[k] || "<td></td>").replace("<td", `<td data-c="${k}"`)).join("")}</tr>`;
  }

  async _liveOnly() {
    // nur die Zeile „Lädt gerade“ nachführen, ohne die ganze Seite neu zu zeichnen (kein Flackern)
    try {
      const data = await this._hass.callWS({ type: "drive_energy_doc/list" });
      const ids = x => (x || []).map(y => y.id).join(",");
      if (!data.length || ids(data) !== ids(this._data)) { this._load(); return; }   // Fahrzeuge (noch) nicht alle da, z. B. während eines Neustarts: nicht übernehmen, normal laden
      this._data = data;
      if (this._dlg || this.shadowRoot.querySelector(".busy, .dlg") || !this._liveCtx) return;
      const v = data[this._tab || 0];
      const lv = v && v.summary && v.summary.live && ["all", "electric", "both", "home"].includes(this._liveCtx.flt) ? v.summary.live : null;
      const tr = this.shadowRoot.querySelector("tr.c-live");
      if (!!lv !== !!tr) { this._sig = JSON.stringify(data); this._render(); return; }   // erscheint oder verschwindet: einmal ganz zeichnen (gezeichneten Stand merken)
      if (lv) {
        const tpl = document.createElement("template");
        tpl.innerHTML = this._liveRowHtml(lv, v, this._liveCtx.u, this._liveCtx.order);
        tr.replaceWith(tpl.content.firstElementChild);
      }
    } catch (e) { /* nächster Versuch beim nächsten Ereignis */ }
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
      if (ev.live) {   // nur die laufende Ladung hat sich geändert
        clearTimeout(this._liveT);
        this._liveT = setTimeout(() => this._liveOnly(), 300);
        return;
      }
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
  set narrow(v) { this._narrow = v; this._menu(); }
  get narrow() { return this._narrow; }
  connectedCallback() {
    // HA kann das Element anlegen und hass setzen, bevor diese Datei geladen ist (Ladedatei lädt sie nach): dann liegt hass als eigene Eigenschaft
    // am Element und verdeckt den Setter – das Panel würde nie laden. Wert übernehmen und über den Setter neu setzen.
    if (Object.prototype.hasOwnProperty.call(this, "hass")) { const h = this.hass; delete this.hass; if (h) this.hass = h; }
    if (Object.prototype.hasOwnProperty.call(this, "narrow")) { const n = this.narrow; delete this.narrow; this.narrow = n; }   // ebenso narrow (Menü-Button am Handy)
    if (!this._locCb) { this._locCb = () => this._quick(); }
    window.addEventListener("location-changed", this._locCb);   // Link aus der Push-Nachricht, während das Panel schon offen ist
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      // ShadowRoot kennt kein onclick: echten Listener setzen
      this.shadowRoot.addEventListener("click", ev => { if (ev.composedPath().includes(this._mb)) return; if (this._cur) this._click(ev, this._cur); });   // Menü-Button öffnet nur die Seitenleiste, nicht die Fahrzeugwahl
      this.shadowRoot.addEventListener("change", ev => { if (ev.target && ev.target.id === "agg") { this._agg = ev.target.value; try { localStorage.setItem("deAgg", this._agg); } catch (e) { /* ignore */ } this._render(); return; } if (ev.target && ev.target.id === "flt") { this._flt = ev.target.value; this._selId = null; this._render(); } });   // Filter der Liste
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
          this._hide = [...DEF_HIDE];
          this._sort = null;
          try { localStorage.setItem(this._ck("deCo"), "null"); localStorage.setItem(this._ck("deHide"), JSON.stringify(this._hide)); localStorage.removeItem("deSort"); } catch (e) { /* ignore */ }
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
        try { localStorage.setItem(this._ck("deCo"), JSON.stringify(o)); } catch (e) { /* ignore */ }
        this._render();
      });
      this.shadowRoot.addEventListener("dragend", () => { this._dragCol = null; this.shadowRoot.querySelectorAll("th.dropt").forEach(x => x.classList.remove("dropt")); });
    }
    this._tab = 0;
    this._hide = [];
    this._agg = "list";
    try { this._agg = localStorage.getItem("deAgg") || "list"; } catch (e) { /* ignore */ }
    try { const h = localStorage.getItem("deHide"); this._hide = h ? (JSON.parse(h) || []) : [...DEF_HIDE]; } catch (e) { /* ignore */ }
    try { if (localStorage.getItem("deHideV") !== "5") { DEF_HIDE.forEach(c => { if (!this._hide.includes(c)) this._hide.push(c); }); localStorage.setItem("deHide", JSON.stringify(this._hide)); localStorage.setItem("deHideV", "5"); } } catch (e) { /* ignore */ }   // neue Spalten zunächst aus
    this._sort = null;   // Sortierung per Klick auf die Spaltenüberschrift: {c: Spalte, dir: 1 aufsteigend | -1 absteigend}
    // Sortierung wird nicht gespeichert: beim Öffnen und beim Fahrzeugwechsel gilt immer der Standard (Nr. absteigend)
    this._cw = {};
    this._co = null;
    try { this._co = JSON.parse(localStorage.getItem("deCo") || "null"); } catch (e) { /* ignore */ }
    try { this._cw = JSON.parse(localStorage.getItem("deCw") || "{}") || {}; } catch (e) { /* ignore */ }
    try { if (localStorage.getItem("deCwV") !== "2") { this._cw = {}; localStorage.setItem("deCw", "{}"); localStorage.setItem("deCwV", "2"); } } catch (e) { /* ignore */ }   // einmalig: alte feste Breiten verwerfen (kompakte Spalten)
    this._ori = "portrait";
    this._rcp = true;
    try { if (localStorage.getItem("deRcp") === "0") this._rcp = false; } catch (e) { /* ignore */ }
    this._clr = true;   // Zeilenfarben: Laden grün, Tanken orange, alles andere blau
    try { if (localStorage.getItem("deClr") === "0") this._clr = false; } catch (e) { /* ignore */ }
    try { if (localStorage.getItem("deOri") === "landscape") this._ori = "landscape"; } catch (e) { /* ignore */ }
    this._render();
    this._timer = setInterval(() => {   // Rückfall, falls ein Ereignis fehlt: nur solange ein Tank- oder Ladevorgang läuft, und dann nur die laufende Zeile
      if (!(this._data || []).length || this._err) this._load();   // noch keine Fahrzeuge (z. B. nach einem Neustart): ganz laden
      else if (this._data.some(x => x.summary && (x.summary.live || (x.summary.status && x.summary.status !== "idle")))) this._liveOnly();
    }, 60000);
    if (this._hass && (!(this._data || []).length || this._err)) this._load();   // wieder eingehängt (HA hängt das Panel z. B. beim Neustart um): ohne Fahrzeuge sofort neu laden
    this._subscribe();   // beim Wiederöffnen der Seite
  }
  disconnectedCallback() {
    clearInterval(this._timer);
    clearTimeout(this._emptyT);
    if (this._locCb) window.removeEventListener("location-changed", this._locCb);
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
      const data = await this._hass.callWS({ type: "drive_energy_doc/list" });
      clearTimeout(this._emptyT);
      if (!data.length) this._emptyT = setTimeout(() => this._load(), 5000);   // direkt nach einem HA-Neustart sind die Fahrzeuge evtl. noch nicht geladen: weiter nachsehen
      if (this._err) { this._err = null; this._sig = null; }
      const sig = JSON.stringify(data);
      if (this._tabInit && sig === this._sig && !this._jumpId && !this._err) return;   // nichts geändert: nicht neu zeichnen (kein Flackern)
      this._data = data;
      if (!this._tabInit) {   // beim ersten Laden das zuletzt gewählte Fahrzeug wieder auswählen
        this._tabInit = true;
        try {
          const i = this._data.findIndex(x => x.id === localStorage.getItem("deVeh"));
          if (i >= 0) this._tab = i;
        } catch (e) { /* ignore */ }
      }
      if (!this._dlg && !this.shadowRoot.querySelector(".busy, .dlg")) {   // nicht neu zeichnen, solange der Fortschritts- oder ein anderer Dialog offen ist
        this._sig = sig;   // gezeichneter Stand
        this._render();
        this._quick();
        if (this._jumpId) { const id = this._jumpId; this._jumpId = null; setTimeout(() => { const r = [...this.shadowRoot.querySelectorAll("tr[data-id]")].find(x => x.dataset.id === id); if (r) { this._selId = id; r.classList.add("rsel"); r.scrollIntoView({ block: "center", behavior: "smooth" }); } }, 50); }   // zur Zeile des gerade erfassten Belegs springen
      } else {   // ein Dialog ist offen: die neuen Daten liegen schon vor, gezeichnet wird nach dem Schließen (nicht verlieren)
        clearTimeout(this._retryT);
        this._retryT = setTimeout(() => this._load(), 2000);
      }
    } catch (e) {
      this._err = String(e.message || e); this._render();
      clearTimeout(this._emptyT);
      this._emptyT = setTimeout(() => this._load(), 5000);   // z. B. Befehl nach dem Neustart noch nicht registriert: erneut versuchen
    }
  }
  _quick() {
    // Link aus der Push-Nachricht „Tankvorgang erkannt“ (?quick=<Fahrzeug>): das Fahrzeug wählen und gleich die Aufnahme anbieten (Kamera oder Galerie). Der Browser erlaubt den Kamera-Start nur nach einem Antippen, darum der große Dialog.
    try {
      const q = new URLSearchParams(location.search).get("quick");
      if (!q || !this._data) return;
      history.replaceState(history.state, "", location.pathname);   // nur einmal auslösen
      const i = this._data.findIndex(x => x.id === q);
      if (i < 0) return;
      this._tab = i;
      this._render();
      setTimeout(() => { if (!this._dlg && !this.shadowRoot.querySelector(".dlg, .busy")) this._pick(this._data[i], null, true); }, 300);
    } catch (e) { /* kein Link, nichts zu tun */ }
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
  _aggHtml(v, ents, mode) {
    // Summen je Zeitraum (beachtet den Filter der Liste); neueste oben, Gesamtsumme unten
    const el = v.energy === "electric", phev = !!v.phev, units = el ? ["kWh"] : phev ? ["l", "kWh"] : ["l"];
    const unitOf = e => (el || (phev && e.energy === "electric")) ? "kWh" : "l";
    const key = ts => {
      const d = new Date(ts * 1000);
      if (mode === "year") return [String(d.getFullYear()), String(d.getFullYear())];
      if (mode === "month") return [`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, d.toLocaleDateString(this._locale || "de-DE", { month: "long", year: "numeric" })];
      const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())), wd = x.getUTCDay() || 7;   // ISO-Kalenderwoche
      x.setUTCDate(x.getUTCDate() + 4 - wd);
      const y = x.getUTCFullYear(), w = Math.ceil(((x - Date.UTC(y, 0, 1)) / 864e5 + 1) / 7);
      return [`${y}-${String(w).padStart(2, "0")}`, `${this.T("KW")} ${w} ${y}`];
    };
    const blank = () => ({ n: 0, total: 0, km: 0, q: { l: 0, kWh: 0 }, qp: { l: 0, kWh: 0 }, tp: { l: 0, kWh: 0 }, cq: { l: 0, kWh: 0 }, ck: { l: 0, kWh: 0 }, wb: 0, wbEst: 0, solQ: 0, solW: 0 });
    const kmOf = {};   // gefahrene km je Eintrag: Abstand zum vorigen Kilometerstand (alle Einträge des Fahrzeugs, unabhängig vom Filter)
    let prevKm = null;
    [...v.entries].filter(x => x.kind !== "extra" && x.odometer != null).sort((a, b) => a.ts - b.ts).forEach(x => { if (prevKm != null && x.odometer > prevKm && x.odometer - prevKm < 5000) kmOf[x.id] = x.odometer - prevKm; prevKm = Math.max(prevKm || 0, x.odometer); });
    const add = (g, e) => {
      if (e.total) g.total += e.total;
      if (e.kind === "extra") return;
      g.n++;
      const u = unitOf(e);
      g.km += kmOf[e.id] || 0;
      if (e.consumption && e.cons_km) { g.cq[u] += e.consumption * e.cons_km / 100; g.ck[u] += e.cons_km; }   // Verbrauch nach Strecke gewichtet
      if (e.quantity) { g.q[u] += e.quantity; if (e.total) { g.qp[u] += e.quantity; g.tp[u] += e.total; } }
      if (e.quantity_source === "wallbox" && e.wb_kwh && e.est_quantity) { g.wb += e.wb_kwh; g.wbEst += e.est_quantity; }
      if (e.solar_pct != null && e.quantity) { g.solQ += e.quantity; g.solW += e.solar_pct * e.quantity; }
    };
    const groups = new Map(), sum = blank();
    ents.forEach(e => { const [k, label] = key(e.ts); if (!groups.has(k)) groups.set(k, { label, ...blank() }); add(groups.get(k), e); add(sum, e); });
    const strom = el || phev;
    const head = [this.T("Zeitraum"), this.T("Einträge"), this.T("km"), ...units.map(u => `${this.T("Menge")} ${this.T(u)}`), ...units.map(u => `${this.T(u)}/100 ${this.T("km")}`), ...units.map(u => `€/${this.T(u)}`), this.T("Betrag"), ...(strom ? [this.T("Solaranteil"), this.T("Ladeverlust")] : [])];
    const row = (g, lab, tag) => `<tr><${tag}>${this._esc(lab)}</${tag}><${tag} class="n">${g.n}</${tag}><${tag} class="n">${g.km ? this._fmt(g.km, 0) : "–"}</${tag}>${units.map(u => `<${tag} class="n">${g.q[u] ? this._fmt(g.q[u]) : "–"}</${tag}>`).join("")}${units.map(u => `<${tag} class="n">${g.ck[u] ? this._fmt(g.cq[u] / g.ck[u] * 100) : "–"}</${tag}>`).join("")}${units.map(u => `<${tag} class="n">${g.qp[u] ? this._fmt(g.tp[u] / g.qp[u], 3) : "–"}</${tag}>`).join("")}<${tag} class="n">${this._fmt(g.total)} €</${tag}>${strom ? `<${tag} class="ctr">${g.solQ ? Math.round(g.solW / g.solQ) + " %" : "–"}</${tag}><${tag} class="n">${g.wbEst ? Math.round((g.wb / g.wbEst - 1) * 100) + " %" : "–"}</${tag}>` : ""}</tr>`;
    const body = [...groups.entries()].sort((a, b) => b[0].localeCompare(a[0])).map(([, g]) => row(g, g.label, "td")).join("");
    return `<div class="wrap"><table class="agg"><thead><tr>${head.map((h, i) => `<th class="${i === 0 ? "" : strom && i === head.length - 2 ? "ctr" : "n"}">${this._esc(h)}</th>`).join("")}</tr></thead><tbody>${body || `<tr><td colspan="${head.length}">–</td></tr>`}</tbody><tfoot>${row(sum, this.T("Summe"), "td")}</tfoot></table></div>`;
  }
  _chart(o) {
    // Liniendiagramm oder Punkte, eine y-Achse. o: {series:[{name,color,pts:[[x,y]],dots}], x:[min,max], y:[min,max], xfmt, yfmt, h}
    const W = 640, H = o.h || 200, L = 46, R = 12, T = 8, B = 24;
    const [x0, x1] = o.x[0] === o.x[1] ? [o.x[0] - 1, o.x[1] + 1] : o.x, [y0, y1] = o.y;
    const X = x => L + (x - x0) / (x1 - x0) * (W - L - R), Y = y => H - B - (y - y0) / ((y1 - y0) || 1) * (H - T - B);
    const yt = [0, 1, 2, 3, 4].map(i => y0 + (y1 - y0) * i / 4), xt = [0, 1, 2, 3, 4].map(i => x0 + (x1 - x0) * i / 4);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">`;
    s += yt.map(v => `<line class="gl" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax" x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${this._esc(o.yfmt(v))}</text>`).join("");
    s += xt.map(v => `<text class="ax" x="${X(v)}" y="${H - 6}" text-anchor="middle">${this._esc(o.xfmt(v))}</text>`).join("");
    for (const sr of o.series) {
      const pts = sr.pts.filter(q => q[1] != null);
      if (!pts.length) continue;
      if (sr.dots) s += pts.map(q => `<circle class="dt" cx="${X(q[0])}" cy="${Y(q[1])}" r="5" fill="${sr.color}"/>`).join("");
      else s += `<path class="ln" stroke="${sr.color}" d="${pts.map((q, i) => (i ? "L" : "M") + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1)).join("")}"/>`;
    }
    s += `<line class="xh" y1="${T}" y2="${H - B}" style="display:none"/></svg>`;
    return { svg: s, X, Y, W, H, L, R, x0, x1 };
  }
  _chartBox(title, legend, c, onHover) {
    // Rahmen mit Titel, Legende (ab zwei Reihen) und Tooltip; onHover(xWert, px, py) liefert {html, x} oder null
    const box = document.createElement("div");
    box.className = "cbox";
    box.innerHTML = `<div class="ttl">${this._esc(title)}</div>${legend.length > 1 ? `<div class="lg">${legend.map(l => `<span><i style="background:${l.color}"></i>${this._esc(l.name)}</span>`).join("")}</div>` : ""}${c.svg}<div class="tip"></div>`;
    const svg = box.querySelector("svg"), tip = box.querySelector(".tip"), xh = box.querySelector(".xh");
    const move = ev => {
      const r = svg.getBoundingClientRect(), sx = (ev.clientX - r.left) / r.width * c.W, sy = (ev.clientY - r.top) / r.height * c.H;
      const xv = c.x0 + (sx - c.L) / (c.W - c.L - c.R) * (c.x1 - c.x0);
      const hit = onHover(xv, sx, sy);
      if (!hit) { tip.style.display = "none"; xh.style.display = "none"; return; }
      if (hit.x != null) { xh.setAttribute("x1", hit.x); xh.setAttribute("x2", hit.x); xh.style.display = ""; }
      tip.innerHTML = hit.html; tip.style.display = "block";
      const bx = box.getBoundingClientRect(), left = ev.clientX - bx.left + 12;
      tip.style.left = Math.min(left, bx.width - tip.offsetWidth - 4) + "px"; tip.style.top = (ev.clientY - bx.top - 34) + "px";
    };
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", () => { tip.style.display = "none"; xh.style.display = "none"; });
    return box;
  }
  async _curveDlg(v, e) {
    // Ladekurve eines Eintrags: Leistung (Wallbox, Auto) und Ladestand, zwei Diagramme mit gemeinsamer Zeitachse
    this._pvHide();
    const dlg = document.createElement("div");
    dlg.className = "dlg curve";
    dlg.innerHTML = `<div class="card"><div class="dh">${this.T("Ladekurve")} · ${this._esc(this._date(e.ts))}</div><div class="bd">…</div><div class="df"><button data-d="ok" class="pri">OK</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const done = () => { dlg.remove(); this._dlg = null; this._render(); };
    dlg.onclick = ev => { ev.stopPropagation(); if (ev.target === dlg || ev.target.closest("[data-d=ok]")) done(); };
    dlg.onkeydown = ev => { if (ev.key === "Escape") done(); };
    let data = null;
    try { data = await this._hass.callWS({ type: "drive_energy_doc/curve", vehicle: v.id, entry: e.id }); } catch (err) { /* keine Kurve */ }
    const bd = dlg.querySelector(".bd");
    if (!data || !data.p || !data.p.length) { bd.textContent = this.T("Keine Ladekurve gespeichert."); return; }
    const pts = data.p.map(q => [data.t0 + q[0], q[1], q[2], q[3]]);
    const xr = [pts[0][0], pts[pts.length - 1][0]], tm = x => this._tm(x);
    const BLUE = "#2a78d6", ORANGE = "#eb6834";
    const wb = { name: "Wallbox", color: BLUE, pts: pts.map(q => [q[0], q[1] != null ? q[1] / 1000 : null]) };
    const car = { name: this.T("Auto"), color: ORANGE, pts: pts.map(q => [q[0], q[2] != null ? q[2] / 1000 : null]) };
    const ser = [wb, car].filter(sr => sr.pts.some(q => q[1] != null));
    const kmax = Math.max(1, ...ser.flatMap(sr => sr.pts.map(q => q[1] || 0)));
    const near = x => pts.reduce((b, q) => Math.abs(q[0] - x) < Math.abs(b[0] - x) ? q : b, pts[0]);
    bd.innerHTML = "";
    const c1 = this._chart({ series: ser, x: xr, y: [0, Math.ceil(kmax / 4) * 4], xfmt: tm, yfmt: y => this._fmt(y, 1) + " kW" });
    bd.appendChild(this._chartBox(this.T("Ladeleistung"), ser, c1, x => { const q = near(x); return { x: c1.X(q[0]), html: `${tm(q[0])}<br>${ser.map(sr => `${this._esc(sr.name)}: ${sr === wb ? (q[1] != null ? this._fmt(q[1] / 1000, 1) : "–") : (q[2] != null ? this._fmt(q[2] / 1000, 1) : "–")} kW`).join("<br>")}` }; }));
    const soc = pts.filter(q => q[3] != null);
    if (soc.length) {
      const lo = Math.max(0, Math.floor(Math.min(...soc.map(q => q[3])) / 10) * 10), hi = Math.min(100, Math.ceil(Math.max(...soc.map(q => q[3])) / 10) * 10);
      const c2 = this._chart({ series: [{ name: this.T("Ladestand"), color: BLUE, pts: soc.map(q => [q[0], q[3]]) }], x: xr, y: [lo, lo + Math.max(20, Math.ceil((hi - lo) / 20) * 20)], xfmt: tm, yfmt: y => Math.round(y) + " %", h: 150 });
      bd.appendChild(this._chartBox(this.T("Ladestand"), [], c2, x => { const q = soc.reduce((b, r) => Math.abs(r[0] - x) < Math.abs(b[0] - x) ? r : b, soc[0]); return { x: c2.X(q[0]), html: `${tm(q[0])}<br>${Math.round(q[3])} %` }; }));
    }
  }
  _lossHtml(v, ents) {
    // Ladeverlust nach mittlerer Ladeleistung: Punktdiagramm (eine Ladung = ein Punkt) und Tabelle je Leistungsbereich
    const rows = ents.filter(e => this._loss(e) != null && this._pavg(e) != null).map(e => ({ e, kw: this._pavg(e), l: this._loss(e) }));
    this._lossRows = rows;
    const BANDS = [[0, 2.3], [2.3, 3.7], [3.7, 7.4], [7.4, 11.1], [11.1, 22.1], [22.1, 1e9]];
    const band = BANDS.map(([a, b]) => { const r = rows.filter(x => x.kw >= a && x.kw < b); const wb = r.reduce((s, x) => s + x.e.wb_kwh, 0), est = r.reduce((s, x) => s + x.e.est_quantity, 0); return { a, b, n: r.length, wb, loss: est ? Math.round((wb / est - 1) * 100) : null }; }).filter(x => x.n);
    const tbl = `<div class="wrap"><table class="agg"><thead><tr><th>${this.T("Ø Ladeleistung")}</th><th class="n">${this.T("Einträge")}</th><th class="n">Wallbox kWh</th><th class="n">${this.T("Ladeverlust")}</th></tr></thead><tbody>${band.map(x => `<tr><td>${this._fmt(x.a, 1)}${x.b < 1e8 ? "–" + this._fmt(x.b, 1) : "+"} kW</td><td class="n">${x.n}</td><td class="n">${this._fmt(x.wb)}</td><td class="n">${x.loss != null ? x.loss + " %" : "–"}</td></tr>`).join("") || `<tr><td colspan="4">–</td></tr>`}</tbody></table></div>`;
    return `<div class="lossv" id="lossv">${rows.length ? "" : this._esc(this.T("Noch keine Ladung mit Wallbox-Menge und Ladeleistung."))}</div>${tbl}`;
  }
  _lossChart() {
    // nach dem Zeichnen: Punktdiagramm in den Platzhalter (mit Tooltip je Punkt)
    const host = this.shadowRoot.getElementById("lossv"), rows = this._lossRows || [];
    if (!host || !rows.length) return;
    const xmax = Math.max(4, Math.ceil(Math.max(...rows.map(r => r.kw)) / 4) * 4), ymin = Math.min(0, Math.floor(Math.min(...rows.map(r => r.l)) / 5) * 5), ymax = Math.max(10, Math.ceil(Math.max(...rows.map(r => r.l)) / 5) * 5);
    const c = this._chart({ series: [{ name: this.T("Ladeverlust"), color: "#2a78d6", dots: true, pts: rows.map(r => [r.kw, r.l]) }], x: [0, xmax], y: [ymin, ymin + Math.ceil((ymax - ymin) / 20) * 20], xfmt: x => this._fmt(x, 1) + " kW", yfmt: y => Math.round(y) + " %", h: 240 });
    host.innerHTML = "";
    host.appendChild(this._chartBox(this.T("Ladeverlust") + " / " + this.T("Ø Ladeleistung"), [], c, (x, sx, sy) => {
      let best = null, bd = 400;
      rows.forEach(r => { const d = (c.X(r.kw) - sx) ** 2 + (c.Y(r.l) - sy) ** 2; if (d < bd) { bd = d; best = r; } });
      return best ? { html: `${this._esc(this._date(best.e.ts))}<br>${this._fmt(best.kw, 1)} kW · ${best.l} %<br>${this._fmt(best.e.wb_kwh)} kWh Wallbox` } : null;
    }));
  }
  _pavg(e) {
    // mittlere Ladeleistung (kW): gespeichert, bei älteren Einträgen aus der Ladeart-Erkennung („mittel“)
    return e.avg_kw != null ? e.avg_kw : (e.charge_src === "mittel" && e.charge_kw ? e.charge_kw : null);
  }
  _pavgEst(e) {
    // ältere Strom-Einträge ohne gespeicherte Leistung: Näherung aus Menge und Dauer (Laden von/bis); Pausen zählen mit, darum nur als „≈“ und nicht in der Auswertung
    if (this._pavg(e) != null || e.kind === "extra" || !e.ts_start || !e.ts || e.ts - e.ts_start < 600) return null;
    const q = e.wb_kwh || e.quantity || e.est_quantity;
    if (!q || (e.energy !== "electric" && !(this._rv && this._rv.energy === "electric"))) return null;
    const kw = q / ((e.ts - e.ts_start) / 3600);
    return kw >= 0.5 && kw <= 400 ? kw : null;
  }
  _ppk(e) {
    // Spitzenleistung (kW): gespeichert, bei älteren Einträgen aus Sensor oder Leistungsmessung
    return e.peak_kw != null ? e.peak_kw : ((e.charge_src === "sensor" || e.charge_src === "leistung") && e.charge_kw ? e.charge_kw : null);
  }
  _dt(ts, ref) {
    // Uhrzeit; liegt sie an einem anderen Tag als der Eintrag, mit Datum
    return new Date(ts * 1000).toDateString() === new Date(ref * 1000).toDateString() ? this._tm(ts) : `<span>${this._d(ts)}</span> <span class="tm">${this._tm(ts)}</span>`;
  }
  _wbNote(e) {
    // Vorschlag für die Notiz einer Heimladung (der Nutzer kann ergänzen; gespeichert wird beim Speichern)
    if (!e || e.quantity_source !== "wallbox" || !e.est_quantity) return "";
    const l = this._loss(e);
    return `${this.T("Akku")} ${this._fmt(e.est_quantity)} kWh · Wallbox ${this._fmt(e.wb_kwh || e.quantity)} kWh${l != null ? ` · ${this.T("Ladeverlust")} ${l} %` : ""}`;
  }
  _loss(e) {
    // Ladeverlust in % aus Wallbox-Menge und Schätzung aus dem Ladestand; None, wenn nicht bestimmbar (kleine Ladung, Anfang fehlt)
    if (e.quantity_source !== "wallbox" || !(e.est_quantity >= 2) || !e.wb_kwh) return null;
    return Math.round((e.wb_kwh / e.est_quantity - 1) * 100);
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

  _ck(k) { return `${k}:${this._colVeh || ""}`; }   // Spalten-Einstellungen je Fahrzeug
  _loadCols(vid) {
    // Spalten (Auswahl, Reihenfolge, Breiten) des Fahrzeugs laden; beim ersten Mal die bisherigen gemeinsamen Einstellungen übernehmen
    const g = this._colsGlobal || (this._colsGlobal = { hide: [...this._hide], co: this._co, cw: { ...this._cw } });
    this._colVeh = vid;
    const rd = (k, dflt) => { try { const s = localStorage.getItem(this._ck(k)); return s != null ? JSON.parse(s) : dflt; } catch (e) { return dflt; } };
    this._hide = rd("deHide", [...g.hide]) || [...DEF_HIDE];
    this._co = rd("deCo", g.co);
    this._cw = rd("deCw", { ...g.cw }) || {};
  }
  _saveCw() {
    try { localStorage.setItem(this._ck("deCw"), JSON.stringify(this._cw)); } catch (e) { /* ignore */ }
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
      palette: '<path d="M12 3a9 9 0 1 0 0 18c1.4 0 2-.9 2-1.8 0-1.6-1.4-1.7-1.4-3 0-1 .8-1.7 1.9-1.7H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7.5" r="1"/><circle cx="14.5" cy="7.5" r="1"/>',
      paletteOff: '<path d="M12 3a9 9 0 1 0 0 18c1.4 0 2-.9 2-1.8 0-1.6-1.4-1.7-1.4-3 0-1 .8-1.7 1.9-1.7H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z"/><path d="M3.5 3.5l17 17"/>',
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
      cal: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
      road: '<path d="M8 3 5 21M16 3l3 18M12 4v3M12 10.5v3M12 17v3"/>',
      pin: '<path d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
      drop: '<path d="M12 3.5s6 6.8 6 10.8a6 6 0 0 1-12 0c0-4 6-10.8 6-10.8z"/>',
      batt: '<rect x="3" y="8" width="18" height="12" rx="1.5"/><path d="M6 8V5.5h3.5V8M14.5 8V5.5H18V8M6.5 14h3.5M15 12.2v3.6M13.2 14h3.6"/>',
      gauge: '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l3.5-5"/>',
      chart: '<path d="M4 4v16h16"/><path d="M7 15l4-5 3 3 5-7"/>',
      check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
      pwr: '<path d="M13 3 6 13h5l-1 8 7-10h-5z"/>',
      pwrPk: '<path d="M11 3 5 13h5l-1 8 7-10h-5z"/><path d="M17 3h4M19 3v5"/>',
      plug: '<path d="M9 3v5M15 3v5M6.5 8h11v3a5.5 5.5 0 0 1-11 0zM12 16.5V21"/>',
      car: '<path d="M4 16v-3.5L6 8h12l2 4.5V16z"/><path d="M4 16v2.5h3V16M17 16v2.5h3V16M6.5 13h2M15.5 13h2"/>',
      wbox: '<rect x="5" y="3" width="10" height="15" rx="2"/><path d="M8 7h4M15 12h2.5a2 2 0 0 1 2 2v3.5a2 2 0 0 1-4 0V21"/>',
      battLow: '<rect x="2.5" y="7" width="16" height="10" rx="2"/><path d="M21 10.5v3M6 10v4"/>',
      battFull: '<rect x="2.5" y="7" width="16" height="10" rx="2"/><path d="M21 10.5v3M6 10v4M9.5 10v4M13 10v4M15.5 10v4"/>',
      clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
      clockEnd: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.5l2.4 2.4 4.6-5"/>',
      sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5V5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
      loss: '<path d="M11 3 5 12h4.5L8.5 19 15 10h-4.5z"/><path d="M19 12v8M16.5 17.5 19 20l2.5-2.5"/>',
      bon: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
      warn: '<path d="M12 4l9 16H3zM12 10v5M12 17.2v.3"/>',
    };
    return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;
  }
  _esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  _render() {
    this._render0();
    if (this._agg === "power") this._lossChart();
    if (this._liveEl && this._liveEl.childElementCount) this._liveWrap();   // Hinweis/Meldung nach dem Neuzeichnen wieder einhängen
  }

  _render0() {
    if (!this.shadowRoot) return;
    const d = this._data || [];
    const v = d[this._tab] || d[0];
    this._rv = v;   // Fahrzeug, das gerade gezeichnet wird
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
      .menu{flex:0 0 auto;margin:-8px 0 -8px -8px;color:var(--primary-text-color);--mdc-icon-button-size:44px}.mbtn{background:none;border:0;padding:10px;cursor:pointer}.head .menu{margin-right:-16px}
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
      table:not(.fx){width:auto}   /* kompakt: Spalten nur so breit wie ihr Inhalt */
      th,td{padding:4px 8px;text-align:left;border-bottom:1px solid var(--divider-color);white-space:nowrap}
      td.n,th.n{text-align:right}
      th.sortable{cursor:pointer;user-select:none}th.sortable:hover{background:var(--secondary-background-color,#f1f1f1)}.si{font-size:10px;margin-left:5px;opacity:.75}
      th{position:sticky;top:0;background:var(--card-background-color);font-weight:500}
      .src{font-size:11px;color:var(--secondary-text-color)}
      .hint{font-size:12px;color:var(--secondary-text-color)}
      .ct{display:inline-block;padding:0 6px;border-radius:8px;font-size:10px;font-weight:700;color:#fff;vertical-align:middle;background:#43a047}.ct.dc{background:#e53935}
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
      .ck{display:flex;align-items:center;gap:12px;padding:8px 4px;font-size:16px;cursor:pointer}
      .cols .card{width:min(440px,94vw);max-height:92vh;max-height:92dvh;overflow:hidden}
      .cols .bd{display:grid;grid-template-columns:1fr 1fr;gap:0 12px;overflow:auto;min-height:0}
      .cols .ck{gap:8px;padding:6px 2px;font-size:14px}.cols .ck .ico{width:18px;height:18px;color:var(--secondary-text-color)}
      .cols .ck .cx{width:18px;text-align:center;font-weight:600;color:var(--secondary-text-color)}
      .cols .df{justify-content:space-between}
      @media (max-width:360px){.cols .bd{grid-template-columns:1fr}}.ck input{padding:0;width:20px;height:20px;border:0;background:none;accent-color:var(--primary-color)}
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
      tbody tr.c-fu,tbody tr.c-fu:hover{background:color-mix(in srgb,#ff9800 22%,var(--card-background-color))}
      tbody tr.c-el,tbody tr.c-el:hover{background:color-mix(in srgb,#43a047 24%,var(--card-background-color))}
      th.ctr,td.ctr{text-align:center}
      .chart{width:100%;height:auto;display:block;font-size:11px;touch-action:none}
      .chart .gl{stroke:var(--divider-color);stroke-width:1}.chart .ax{fill:var(--secondary-text-color)}
      .chart .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.chart .dt{stroke:var(--card-background-color,#fff);stroke-width:2}
      .chart .xh{stroke:var(--secondary-text-color);stroke-width:1;stroke-dasharray:3 3}
      .cbox{position:relative;margin:4px 0 10px}.cbox .ttl{font-size:13px;font-weight:500;margin-bottom:2px}
      .cbox .lg{display:flex;gap:14px;font-size:12px;color:var(--secondary-text-color);margin-bottom:2px}.cbox .lg i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
      .tip{position:absolute;pointer-events:none;background:var(--card-background-color,#fff);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:6px;padding:4px 7px;font-size:12px;white-space:nowrap;box-shadow:0 2px 6px #0003;display:none;z-index:2}
      .curve .card{width:min(760px,96vw);max-height:92vh;max-height:92dvh;overflow:auto}
      .lossv{background:var(--card-background-color);border-radius:10px;padding:10px 12px;margin-bottom:10px;max-width:760px}
      table.agg tfoot td{font-weight:600;border-top:2px solid var(--divider-color);border-bottom:0}
      .sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
      thead th .ico{width:18px;height:18px;vertical-align:-4px}
      tbody tr.c-home,tbody tr.c-home:hover{background:color-mix(in srgb,#fdd835 38%,var(--card-background-color))}
      tbody tr.c-ex,tbody tr.c-ex:hover{background:color-mix(in srgb,#1e88e5 22%,var(--card-background-color))}
      tbody tr.c-live,tbody tr.c-live:hover{background:color-mix(in srgb,#00acc1 28%,var(--card-background-color))}
      tbody tr.c-live .pulse{display:inline-block;width:.6em;height:.6em;border-radius:50%;background:#00acc1;margin-right:.4em;animation:pls 1.4s ease-in-out infinite}
      @keyframes pls{50%{opacity:.25}}
      @media (prefers-reduced-motion:reduce){tbody tr.c-live .pulse{animation:none}}
      tbody tr.rsel,tbody tr.rsel:hover{background:color-mix(in srgb,var(--primary-color) 30%,var(--card-background-color));outline:2px solid var(--primary-color);outline-offset:-2px}
      tbody tr.rsel td:first-child{box-shadow:inset 5px 0 0 var(--primary-color)}
      .livebn{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:130;display:flex;align-items:center;gap:12px;padding:12px 18px;border-radius:12px;background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 4px 18px rgba(0,0,0,.35);font-size:16px}
      .livetoast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:130;width:min(560px,92vw);padding:14px 38px 14px 16px;border-radius:12px;background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 4px 18px rgba(0,0,0,.4);border-left:6px solid var(--primary-color);font-size:15px;line-height:1.4;box-sizing:border-box}
      .livebn .spin{width:26px;height:26px;border-width:4px}
      .livetoast .h{font-weight:600;margin-bottom:4px}.livetoast .x{position:absolute;top:6px;right:8px;border:0;background:none;color:inherit;font-size:24px;cursor:pointer;line-height:1}
      .wq{display:inline-flex;vertical-align:middle;color:var(--secondary-text-color);cursor:help}.wq .ico{width:16px;height:16px;stroke-width:2}
      td.est,span.est{color:var(--secondary-text-color);font-style:italic}
      .wtri{display:inline-flex;vertical-align:middle;color:var(--warning-color,#e67e22);cursor:help}.wtri .ico{width:16px;height:16px;stroke-width:2.2}
      .bar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
      .bar .flt{font-size:14px;padding:8px 10px;border:1px solid var(--divider-color,#ccc);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color);max-width:46vw}
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
    if (this._err) { this.shadowRoot.innerHTML = `<style>${css}</style><p>${this._esc(this._err)}</p>`; this._menu(); return; }
    if (!d.length) { this.shadowRoot.innerHTML = `<style>${css}</style><h1>Drive Energy Doc</h1><p>${this.T("Noch kein Fahrzeug. Einstellungen → Geräte & Dienste → Integration „Drive Energy Doc“ hinzufügen.")}</p>`; this._menu(); return; }
    if (v.id !== this._colVeh) this._loadCols(v.id);
    const s = v.summary, u = this.T(v.unit);
    const pic = this._pic(v);
    const cw = this._cw || {};
    const fixed = COLS.some(c => cw[c]);
    const hasSol = v.energy === "electric" || !!v.phev, hasLoss = hasSol;   // Solaranteil und Ladeverlust nur bei Elektroauto und Plug-in-Hybrid
    const order = this._order().filter(c => c === "act" || !this._hide.includes(c)).filter(c => (c !== "sol" || hasSol) && (c !== "loss" || hasLoss) && (!["start", "end", "lfrom", "lto", "ctype", "kcar", "kwb", "pavg", "ppk"].includes(c) || hasSol));   // ausgeblendete Spalten weglassen; Solar und Ladeverlust nur bei Strom
    const sumW = order.reduce((t, c) => t + (cw[c] || DEFW[c] || 120), 0);
    const nums = {};
    [...v.entries].filter(x => x.kind !== "extra").sort((a, b) => a.ts - b.ts).forEach((x, i) => { nums[x.id] = i + 1; });
    this._nums = nums;   // für die Hinweise der Warndreiecke (z. B. „doppelt zu Nr. 4“)   // laufende Nummer der Tankvorgänge, ältester = 1
    const sk = this._sort && COLS.includes(this._sort.c) ? this._sort : { c: "nr", dir: -1 };   // Standard: nach Nummer absteigend (neueste oben)
    const nrKey = {};   // Zubehör hat keine Nummer: es steht direkt hinter dem davor liegenden Tankvorgang, damit die Reihenfolge zeitlich stimmt
    { let last = 0; [...v.entries].sort((a, b) => a.ts - b.ts).forEach(x => { if (nums[x.id]) last = nums[x.id]; nrKey[x.id] = nums[x.id] || last + 0.5; }); }
    const skey = (e, c) => ({ nr: nrKey[e.id], date: e.ts, km: e.odometer, station: (e.station || "").toLowerCase(), qty: e.quantity, price: e.unit_price, total: e.total, cons: e.consumption, start: e.ts_start, end: e.ts_start ? e.ts : null, lfrom: e.level_from, lto: e.level_to, ctype: e.charge_type || "", kcar: e.est_quantity, kwb: e.wb_kwh, pavg: this._pavg(e), ppk: this._ppk(e), sol: e.solar_pct, loss: this._loss(e), receipt: (e.photo_urls || []).length, note: (e.note || "").toLowerCase() })[c];
    const none = x => x == null || x === "" || (typeof x === "number" && isNaN(x));
    const list = [...v.entries].sort((a, b) => {   // leere Werte stehen immer unten, egal in welche Richtung
      const x = skey(a, sk.c), y = skey(b, sk.c);
      if (none(x) && none(y)) return 0;
      if (none(x)) return 1;
      if (none(y)) return -1;
      return (typeof x === "string" ? x.localeCompare(y, this._locale || "de") : x - y) * sk.dir;
    });
    const PRE = [["oil", "Öl", ["öl", "oel", "oil"]], ["adblue", "AdBlue", ["adblue"]], ["washer", "Scheibenreiniger", ["scheibenreiniger", "scheibenwasser", "washer"]], ["wash", "Waschen", ["wasch", "wäsch", "wash"]]];
    const isHome = e => e.kind !== "extra" && (e.quantity_source === "wallbox" || e.price_source === "Wallbox");   // an der Heim-Wallbox geladen
    const catOf = e => {   // Gruppe eines Eintrags für den Filter
      if (e.kind !== "extra") return e.energy === "electric" || v.energy === "electric" ? "electric" : "fuel";
      const low = String(e.item || "").toLowerCase();
      const hit = PRE.find(x => x[2].some(m => low.includes(m)));
      return hit && (hit[0] !== "adblue" || v.energy === "diesel") ? hit[0] : "other";   // AdBlue gibt es nur beim Diesel, sonst zählt es unter Sonstiges
    };
    const cnt = {}; v.entries.forEach(e => { const c = catOf(e); cnt[c] = (cnt[c] || 0) + 1; if (e.kind === "extra") cnt.extra = (cnt.extra || 0) + 1; else cnt.both = (cnt.both || 0) + 1; if (isHome(e)) cnt.home = (cnt.home || 0) + 1; });
    const FLT = [["all", this.T("Alle")], ["fuel", this.T("Tanken")], ["electric", this.T("Laden")], ["home", this.T("Heimladen")], ["both", this.T("Tanken & Laden")], ["extra", this.T("Zubehör")], ["oil", this.T("Öl")], ["adblue", "AdBlue"], ["washer", this.T("Scheibenreiniger")], ["wash", this.T("Waschen")], ["other", this.T("Sonstiges")]]
      .filter(([k]) => k === "all" || (k === "both" ? cnt.fuel && cnt.electric : cnt[k]));   // nur Gruppen, zu denen es Einträge gibt
    let flt = FLT.some(x => x[0] === this._flt) ? this._flt : "all";
    const shown = flt === "all" ? list : list.filter(e => flt === "extra" ? e.kind === "extra" : flt === "both" ? e.kind !== "extra" : flt === "home" ? isHome(e) : catOf(e) === flt);
    const AGG = [["list", this.T("Liste")], ["week", this.T("Woche")], ["month", this.T("Monat")], ["year", this.T("Jahr")], ...(v.energy === "electric" || v.phev ? [["power", this.T("Verlust nach Leistung")]] : [])];
    const agg = AGG.some(x => x[0] === this._agg) ? this._agg : "list";
    const aggSel = `<select id="agg" class="flt" title="${this.T("Summen")}" aria-label="${this.T("Summen")}">${AGG.map(([k, l]) => `<option value="${k}"${k === agg ? " selected" : ""}>${this._esc(l)}</option>`).join("")}</select>`;
    const aggHtml = agg === "list" ? "" : agg === "power" ? this._lossHtml(v, shown) : this._aggHtml(v, shown, agg);
    const fltSel = FLT.length < 2 ? "" : `<select id="flt" class="flt" title="${this.T("Filter")}" aria-label="${this.T("Filter")}">${FLT.map(([k, l]) => `<option value="${k}"${k === flt ? " selected" : ""}>${this._esc(l)}${k === "all" ? "" : " (" + (cnt[k] || 0) + ")"}</option>`).join("")}</select>`;
    this._shownIds = flt === "all" ? null : new Set(shown.map(e => e.id)); this._fltLabel = (FLT.find(x => x[0] === flt) || [])[1] || "";   // der Ausdruck übernimmt den Filter
    const rows = shown.map(e => {
      const cell = {
        nr: `<td class="n nr">${nums[e.id] || ""}</td>`,
        date: `<td data-nr="${nums[e.id] ? "#" + nums[e.id] : ""}"><span>${this._d(e.ts)}</span><span class="tm">${this._tm(e.ts)}</span></td>`,
        km: `<td class="n${e.odometer_source === "bekannt" ? " est" : ""}"${e.odometer_source === "bekannt" ? ` title="${this._esc(this.T("Kilometerstand"))} (≈)"` : ""}>${e.odometer != null ? this._fmt(e.odometer, 0) : "–"}${this._warn(e, "km", v)}</td>`,
        station: `<td><div>${this._esc(e.station || "")}</div><div class="src">${this._esc(e.address || "")}</div><div class="src gps">${this._gps(e)}</div></td>`,
        qty: `<td class="n">${e.quantity != null ? this._fmt(e.quantity) + " " + (e.kind === "extra" ? this._esc(e.unit || "") : (v.phev && e.energy === "electric" ? "kWh" : u)) : "–"}<div class="src">${e.fuel && e.kind !== "extra" ? this._esc(FUEL_GRADES[e.fuel] || "") + " " : ""}${e.level_from != null && e.level_to != null ? Math.round(e.level_from) + "→" + Math.round(e.level_to) + " %" : (e.increase != null ? "+" + Math.round(e.increase) + " %" : "")} ${e.quantity_source === "wallbox" ? "" : `<span${e.est_factor ? ` title="×${this._fmt(e.est_factor, 2)}"` : ""}>${this._esc(this.T(e.quantity_source || ""))}</span>`}${e.charge_type ? ` <span class="ct ${e.charge_type}" title="${this._esc(this.T("Ladeart") + " " + e.charge_type.toUpperCase() + " · " + this.T({ sensor: "Sensor des Autos", beleg: "beleg", manuell: "manuell", leistung: "Spitzenleistung", mittel: "mittlere Leistung" }[e.charge_src] || "") + (e.charge_kw ? " · " + this._fmt(e.charge_kw, 1) + " kW" : ""))}">${e.charge_type.toUpperCase()}</span>` : ""}</div></td>`,
        price: `<td class="n">${this._fmt(e.unit_price, 3)}${this._warn(e, "price", v)}<div class="src">${this._esc(this.T(e.price_source || ""))}</div></td>`,
        total: `<td class="n">${this._fmt(e.total)} €${this._warn(e, "total", v)}</td>`,
        cons: `<td class="n">${e.consumption != null ? this._fmt(e.consumption) + (v.phev ? `<div class="src">${e.energy === "electric" ? "kWh" : u}/100 ${this.T("km")}</div>` : "") : "–"}${this._warn(e, "cons", v)}</td>`,
        receipt: (() => { const ph = e.photo_urls || [], im = (p, k) => `<img class="${k}" src="${p}" data-p="${p}" data-entry="${e.id}" data-name="${this._esc((e.photos || [])[ph.indexOf(p)] || "")}"${ph.length > 1 && k === "thumb" ? ` data-multi="${e.id}"` : ""} alt="${ph.indexOf(p) === 0 && e.receipt ? this.T("Beleg") : this.T("Zusatzfoto")}">`; return `<td>${ph.length ? im(ph[0], "thumb") : ""}${e.receipt || e.quantity_source === "wallbox" ? "" : `<span class="no" title="${this.T("Beleg fehlt")}">${this._ico("warn")}</span>`}</td>`; })(),
        start: `<td>${e.ts_start && e.kind !== "extra" ? this._dt(e.ts_start, e.ts) : ""}</td>`,
        end: `<td>${e.ts_start && e.kind !== "extra" ? this._dt(e.ts, e.ts) : ""}</td>`,
        lfrom: `<td class="n">${e.level_from != null && e.kind !== "extra" ? Math.round(e.level_from) + " %" : ""}</td>`,
        lto: `<td class="n">${e.level_to != null && e.kind !== "extra" ? Math.round(e.level_to) + " %" : ""}</td>`,
        ctype: `<td class="ctr">${e.charge_type ? `<span class="ct ${e.charge_type}">${e.charge_type.toUpperCase()}</span>` : ""}</td>`,
        kcar: `<td class="n">${e.est_quantity != null && e.kind !== "extra" && (e.energy === "electric" || v.energy === "electric") ? this._fmt(e.est_quantity) + " kWh" : ""}</td>`,
        pavg: `<td class="n">${this._pavg(e) != null ? this._fmt(this._pavg(e), 1) + " kW" : (this._pavgEst(e) != null ? `<span class="src" title="${this._esc(this.T("Näherung aus Menge und Ladedauer (Pausen zählen mit)"))}">≈ ${this._fmt(this._pavgEst(e), 1)} kW</span>` : "")}</td>`,
        ppk: `<td class="n">${this._ppk(e) != null ? this._fmt(this._ppk(e), 1) + " kW" : ""}</td>`,
        kwb: `<td class="n">${e.wb_kwh != null ? this._fmt(e.wb_kwh) + " kWh" : ""}</td>`,
        sol: `<td class="ctr">${e.solar_pct != null ? Math.round(e.solar_pct) + " %" : ""}</td>`,
        loss: (() => { const l = this._loss(e); return `<td class="n"${e.quantity_source === "wallbox" && e.est_quantity ? ` title="${this._fmt(e.wb_kwh)} kWh Wallbox / ${this._fmt(e.est_quantity)} kWh ${this._esc(this.T("Akku"))}"` : ""}>${l != null ? (l < 0 ? `<span class="est">${l} %</span>` : l + " %") : (e.quantity_source === "wallbox" ? "–" : "")}</td>`; })(),
        note: (() => { const full = [e.kind === "extra" ? (e.item || this.T("Zubehör")) : "", e.note || ""].filter(Boolean).join("\n"); return `<td>${full ? `<span class="notec" data-note="${this._esc(full)}">` : ""}${e.kind === "extra" ? `<span class="tag">${this._esc(e.item || this.T("Zubehör"))}</span> ` : ""}${e.note ? `<span class="notei" tabindex="0" role="button" aria-label="${this.T("Notiz anzeigen")}">${this._ico("note")}</span>` : ""}${full ? "</span>" : ""}${e.quantity_source === "wallbox" && e.est_quantity && !e.note ? `<div class="src">${this._esc(this.T("Akku"))} ${this._fmt(e.est_quantity)} kWh</div><div class="src">Wallbox ${this._fmt(e.wb_kwh || e.quantity)} kWh</div>` : ""}</td>`; })(),
        act: `<td>${e.curve ? `<button data-act="curve" title="${this.T("Ladekurve")}" aria-label="${this.T("Ladekurve")}">${this._ico("chart")}</button> ` : ""}<button data-act="edit" title="${this.T("Bearbeiten")}" aria-label="${this.T("Bearbeiten")}">${this._ico("edit")}</button> <button data-act="del" title="${this.T("Eintrag löschen")}" aria-label="${this.T("Eintrag löschen")}">${this._ico("trash")}</button></td>`,
      };
      return `<tr data-id="${e.id}" class="${this._clr ? (e.kind === "extra" ? "c-ex" : isHome(e) ? "c-home" : (catOf(e) === "electric" ? "c-el" : "c-fu")) : ""}${this._selId === e.id ? " rsel" : ""}">${order.map(k => cell[k].replace("<td", `<td data-c="${k}"`)).join("")}</tr>`;
    }).join("");
    const lv = s.live && (flt === "all" || flt === "electric" || flt === "both" || flt === "home") ? s.live : null;   // laufende Ladung: türkise Zeile ganz oben
    const liveRow = lv ? this._liveRowHtml(lv, v, u, order) : "";
    this._liveCtx = { u, order, flt };
    this.shadowRoot.innerHTML = `<style>${css}</style>
      <div class="head${d.length > 1 ? " pick" : ""}"${d.length > 1 ? ` role="button" tabindex="0"` : ""}><div class="ttl"><img class="logo" src="/drive_energy_doc_static/icon.png?v=${VERSION}" alt=""><div><div class="app">Drive Energy Doc</div><h1>${this._esc(this._title(v))}${d.length > 1 ? ` <span class="chev">▾</span>` : ""}</h1></div>${v.plate ? this._plate(v) : ""}</div>${pic ? `<img class="car" src="${this._esc(pic)}" alt="${this._esc(v.name)}">` : ""}</div>
      <div class="sum">
        <div><b>${this._fmt(s.avg_consumption)}</b><span>${u}/100 ${this.T("km")} (${this.T("Ø letzte 5")})</span></div>
        ${v.phev ? `<div><b>${this._fmt(s.avg_consumption_electric)}</b><span>kWh/100 ${this.T("km")} (${this.T("Ø letzte 5")})</span></div>` : ""}
        <div><b>${this._fmt(s.cost_12m)} €</b><span>${this.T("Kosten 12 Monate")}</span></div>
        <button class="shoot" data-act="shoot" title="${this.T("Beleg fotografieren oder hochladen")}" aria-label="${this.T("Beleg fotografieren")}">${this._ico("camera")}<span>${this.T("Beleg / km Stand fotografieren")}</span></button>
      </div>
      <div class="bar"><button data-act="csv" title="${this.T("CSV-Export")}" aria-label="${this.T("CSV-Export")}">${this._ico("csv")}</button><button data-act="print" title="${this.T("Drucken / PDF")}" aria-label="${this.T("Drucken")}">${this._ico("print")}</button><button data-act="ori" title="${this._ori === "portrait" ? this.T("Hochformat") : this.T("Querformat")} (${this.T("zum Wechseln klicken")})" aria-label="${this.T("Seitenformat")}">${this._ico(this._ori)}</button><button data-act="rcp" title="${this.T("Belege im Druck")}: ${this._rcp ? this.T("mit") : this.T("ohne")} (${this.T("zum Wechseln klicken")})" aria-label="${this.T("Belege im Druck")}" aria-pressed="${this._rcp}">${this._ico(this._rcp ? "photo" : "photoOff")}</button><button data-act="clr" title="${this.T("Zeilenfarben")}: ${this._clr ? this.T("an") : this.T("aus")} (${this.T("zum Wechseln klicken")})" aria-label="${this.T("Zeilenfarben")}" aria-pressed="${this._clr}">${this._ico(this._clr ? "palette" : "paletteOff")}</button><button data-act="cols" title="${this.T("Spalten")}" aria-label="${this.T("Spalten")}">${this._ico("cols")}</button><button data-act="add" title="${this.T("Eintrag von Hand hinzufügen")}" aria-label="${this.T("Eintrag von Hand")}">${this._ico("plus")}</button>${aggSel}${fltSel}${(() => { const c = (s.correction || {}); return ["electric", "fuel"].filter(k => c[k] && c[k].all && c[k].all.factor).map(k => { const row = c[k], tip = ["all", "ac", "dc"].filter(g => row[g]).map(g => (g === "all" ? "" : g.toUpperCase() + " ") + (row[g].factor ? "×" + this._fmt(row[g].factor, 2) : "–") + " (" + row[g].n + " " + this.T("Einträge") + ")").join(" · "); return `<span class="stat" title="${this._esc(tip)}"><b>×${this._fmt(row.all.factor, 2)}</b><span>${this.T("Korrektur")} ${this.T(k === "electric" ? "Strom" : "Kraftstoff")}</span></span>`; }).join(""); })()}<span class="stat"><b>${s.count}</b><span>${this.T("Einträge")}</span></span><span class="stat"><b>${this.T(s.status === "refuelling" && (v.energy === "electric" || s.live) ? "Lädt gerade" : { idle: "Bereit", candidate: "Anstieg erkannt", refuelling: "Tankt" }[s.status])}</b><span>${this.T("Status")}</span></span><input type="file" id="cam" accept="image/*" capture="environment" hidden><input type="file" id="pic" accept="image/*" multiple hidden></div>
      ${aggHtml || `<div class="wrap"><table class="${fixed ? "fx" : ""}" ${fixed ? `style="width:${sumW}px"` : ""}><colgroup>${order.map(c => `<col data-c="${c}" ${cw[c] || (fixed && DEFW[c]) ? `style="width:${cw[c] || DEFW[c]}px"` : ""}>`).join("")}</colgroup><thead><tr>${order.map(c => { const sym = (ic, txt) => `${this._ico(ic)}<span class="sr">${this._esc(txt)}</span>`; const H = { nr: ["#", "n"], date: [sym("cal", this.T("Datum")), ""], km: [sym("road", this.T("km")), "n"], station: [sym("pin", this.T("Tankstelle")), ""], qty: [sym(v.energy === "electric" ? "batt" : "drop", this.T("Menge")), "n"], price: [`€/${u}`, "n"], total: ["€", "n"], cons: [sym("gauge", `${u}/100 ${this.T("km")}`), "n"], sol: [sym("sun", this.T("Solaranteil")), "ctr"], start: [sym("clock", this.T("Laden von")), ""], end: [sym("clockEnd", this.T("Laden bis")), ""], lfrom: [sym("battLow", this.T("Ladestand von")), "n"], lto: [sym("battFull", this.T("Ladestand bis")), "n"], ctype: [sym("plug", this.T("Ladeart")), "ctr"], kcar: [sym("car", this.T("Akku") + " kWh"), "n"], kwb: [sym("wbox", "Wallbox kWh"), "n"], pavg: [sym("pwr", this.T("Ø Ladeleistung")), "n"], ppk: [sym("pwrPk", this.T("Spitzenleistung")), "n"], loss: [sym("loss", this.T("Ladeverlust")), "n"], receipt: [sym("bon", this.T("Beleg")), ""], note: [sym("note", this.T("Notiz")), ""], act: ["", ""] }[c]; return `<th data-c="${c}" class="${H[1]}${c === "act" ? "" : " sortable"}" ${sk && sk.c === c ? `aria-sort="${sk.dir > 0 ? "ascending" : "descending"}"` : ""} ${c === "act" ? "" : `draggable="true" title="${this._esc(this._colName(c, u))} · ${this.T("Auf eine andere Überschrift ziehen: Reihenfolge ändern")}"`}>${H[0]}${sk && sk.c === c ? `<span class="si">${sk.dir > 0 ? "▲" : "▼"}</span>` : ""}<span class="rs" data-c="${c}" title="${this.T("Ziehen: Spaltenbreite ändern · Doppelklick: Breiten und Reihenfolge zurücksetzen")}"></span></th>`; }).join("")}</tr></thead><tbody>${liveRow}${rows}</tbody></table></div>`}
      <div class="ver">Drive Energy Doc ${VERSION}</div>`;
    this._menu();
    this._cur = v;
    this.setAttribute("dir", this._rtl ? "rtl" : "ltr");
  }

  _select(id, scroll) {   // Zeilen-Cursor: die markierte Zeile bleibt, bis eine andere gewählt wird (Klick oder Pfeiltasten)
    this._selId = id;
    this.shadowRoot.querySelectorAll("tr.rsel").forEach(x => x.classList.remove("rsel"));
    const r = [...this.shadowRoot.querySelectorAll("tbody tr[data-id]:not(.c-live)")].find(x => x.dataset.id === id);
    if (r) { r.classList.add("rsel"); if (scroll) r.scrollIntoView({ block: "nearest" }); }
  }

  _keys(ev) {
    if (ev.key === "Enter") {   // Enter bei einer markierten Zeile öffnet den Dialog zum Bearbeiten (nicht, wenn gerade ein Knopf, Link oder Eingabefeld den Fokus hat)
      if (this._dlg || this.shadowRoot.querySelector(".dlg, .busy") || /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test((ev.composedPath()[0] || {}).tagName || "")) return;
      const v = this._data && this._data[this._tab], e = v && this._selId && v.entries.find(x => x.id === this._selId);
      if (!e) return;
      ev.preventDefault();
      this._form(v, e);
      return;
    }
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    if (this._dlg || this.shadowRoot.querySelector(".dlg, .busy") || /^(INPUT|SELECT|TEXTAREA)$/.test((ev.composedPath()[0] || {}).tagName || "")) return;
    const rows = [...this.shadowRoot.querySelectorAll("tbody tr[data-id]:not(.c-live)")];
    if (!rows.length) return;
    let i = rows.findIndex(x => x.dataset.id === this._selId);
    i = i < 0 ? (ev.key === "ArrowDown" ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + (ev.key === "ArrowDown" ? 1 : -1)));
    ev.preventDefault();
    this._select(rows[i].dataset.id, true);
  }

  async _click(ev, v) {
    const rowEl = ev.target.closest ? ev.target.closest("tr[data-id]") : null;
    if (rowEl && rowEl.closest("tbody") && rowEl.dataset.id !== "live") this._select(rowEl.dataset.id);   // Klick setzt den Zeilen-Cursor
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
    if (act === "clr") {
      this._clr = !this._clr;
      try { localStorage.setItem("deClr", this._clr ? "1" : "0"); } catch (e) { /* ignore */ }
      return this._render();
    }
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
    if (id === "live" && act === "curve") return this._curveDlg(v, { id: "live", ts: (v.summary.live || {}).ts_start || Date.now() / 1000 });
    if (id === "live" && act === "finish") {
      if (confirm(this.T("Laufende Ladung jetzt abschließen? Lädt das Auto weiter, beginnt danach eine neue Ladung."))) {
        try { await this._hass.callWS({ type: "drive_energy_doc/finish_charge", vehicle: v.id }); } catch (err) { alert(String(err.message || err)); }
        this._sig = null; this._load();
      }
      return;
    }
    const e = v.entries.find(x => x.id === id);
    if (act === "del") {
      if (confirm(this.T("Eintrag vom {0} endgültig löschen?", this._date(e.ts)))) { await this._hass.callWS({ type: "drive_energy_doc/delete", vehicle: v.id, entry: id }); this._load(); }
    } else if (act === "edit") this._form(v, e);
    else if (act === "curve") this._curveDlg(v, e);
  }

  _vehDlg() {
    // Auswahl des Fahrzeugs: Dialog mit allen Fahrzeugen (Kennzeichen, Typ, Name)
    this._pvHide();
    const d = this._data || [];
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card">${d.map((x, i) => `<div class="vo${i === this._tab ? " on" : ""}" data-v="${i}" role="button" tabindex="0">${x.plate ? this._plate(x, true) : ""}<div><div class="tt">${this._esc(this._title(x))}</div>${x.name && this._title(x) !== x.name ? `<div class="nm">${this._esc(x.name)}</div>` : ""}</div>${this._pic(x) ? `<img class="vopic" src="${this._esc(this._pic(x))}" alt="">` : ""}</div>`).join("")}<div class="df"><button data-d="cancel">${this.T("Abbrechen")}</button></div></div>`;
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
    return { nr: this.T("Nr."), date: this.T("Datum"), km: this.T("km"), station: this.T("Tankstelle"), qty: this.T("Menge"), price: `€/${u}`, total: this.T("Betrag"), cons: `${u}/100 ${this.T("km")}`, start: this.T("Laden von"), end: this.T("Laden bis"), lfrom: this.T("Ladestand von"), lto: this.T("Ladestand bis"), ctype: this.T("Ladeart") + " AC/DC", kcar: this.T("Akku") + " kWh", kwb: "Wallbox kWh", pavg: this.T("Ø Ladeleistung"), ppk: this.T("Spitzenleistung"), sol: this.T("Solaranteil"), loss: this.T("Ladeverlust"), receipt: this.T("Beleg"), note: this.T("Notiz") }[c] || c;
  }

  _colIcon(c, v) {
    // dasselbe Symbol wie in der Überschrift
    const I = { date: "cal", start: "clock", end: "clockEnd", lfrom: "battLow", lto: "battFull", ctype: "plug", kcar: "car", kwb: "wbox", pavg: "pwr", ppk: "pwrPk", km: "road", station: "pin", qty: v.energy === "electric" ? "batt" : "drop", cons: "gauge", sol: "sun", loss: "loss", receipt: "bon", note: "note" };
    return I[c] ? this._ico(I[c]) : `<span class="cx">${c === "nr" ? "#" : "€"}</span>`;
  }

  _colsDlg(v) {
    // Spalten ein- und ausblenden (pro Browser gemerkt); die Knöpfe ganz rechts bleiben immer. Nur Spalten, die es beim Fahrzeug gibt.
    this._pvHide();
    const u = this.T(v.unit), el = v.energy === "electric" || !!v.phev;
    const cols = this._order().filter(c => c !== "act" && (el || !["start", "end", "lfrom", "lto", "ctype", "kcar", "kwb", "pavg", "ppk", "sol", "loss"].includes(c)));
    const dlg = document.createElement("div");
    dlg.className = "dlg cols";
    const list = () => cols.map(c => `<label class="ck"><input type="checkbox" data-col="${c}" ${this._hide.includes(c) ? "" : "checked"}>${this._colIcon(c, v)}<span>${this._esc(this._colName(c, u))}</span></label>`).join("");
    dlg.innerHTML = `<div class="card"><div class="dh">${this.T("Spalten")}</div><div class="bd">${list()}</div><div class="df"><button data-d="def">${this.T("Standard")}</button><button data-d="ok" class="pri">OK</button></div></div>`;
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    const save = () => { try { localStorage.setItem(this._ck("deHide"), JSON.stringify(this._hide)); } catch (e) { /* ignore */ } };
    const done = () => { dlg.remove(); this._dlg = null; this._render(); };
    dlg.onchange = ev => {
      const cb = ev.target.closest("[data-col]");
      if (!cb) return;
      this._hide = this._hide.filter(x => x !== cb.dataset.col);
      if (!cb.checked) this._hide.push(cb.dataset.col);
      save();
    };
    dlg.onclick = ev => {
      ev.stopPropagation();
      if (ev.target.closest("[data-d=def]")) { this._hide = [...DEF_HIDE]; save(); dlg.querySelector(".bd").innerHTML = list(); return; }   // Standard: alles an außer „Laden von/bis“
      if (ev.target === dlg || ev.target.closest("[data-d=ok]")) done();
    };
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
      dlg.innerHTML = `<div class="card"><div class="bd"><div class="hd"><div class="mark${awaiting ? " q" : warn ? " w" : ""}">${awaiting ? "?" : warn ? "!" : "✓"}</div><div class="ttl">${this._esc(head)}</div></div><div class="mid">${shot ? `<img class="rshot" src="${this._esc(shot)}" alt="">` : ""}${rows ? `<div class="rows">${rows}</div>` : ""}${pic ? `<img class="rpic" src="${this._esc(pic)}" alt="">` : ""}</div>${ask ? `<div class="ask">${this._esc(ask)}</div>` : ""}${awaiting && !answers.includes("yes") ? `<input id="ra" type="text" placeholder="${answers.includes("km") ? "km 61240" : this._esc(this.T("Antwort (Datum z. B. 27.10. oder „neu“):"))}" autocomplete="off">` : ""}</div><div class="df">${answers.includes("del") ? `<button data-d="del">${this.T("Löschen")}</button>` : ""}${answers.includes("doc") ? `<button data-d="doc">${this.T("Nur Dokumentation")}</button>` : ""}${answers.includes("no") ? `<button data-d="no">${this.T(answers.includes("yes") ? "Nein" : "Abbrechen")}</button>` : ""}${answers.includes("new") ? `<button data-d="new"${answers.includes("yes") ? ' class="pri"' : ""}>${this.T("Neuer Eintrag")}</button>` : ""}${answers.includes("yes") ? `<button data-d="yes"${answers.includes("new") ? "" : ' class="pri"'}>${this.T("Ja")}</button>` : `<button data-d="ok" class="pri">OK</button>`}</div></div>`;
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

  _busyHtml(v, shot, i = 0, total = 1, strip = "") {
    // Der Standard-Fortschrittsdialog beim Lesen eines Belegs: Fahrzeugbild, Kennzeichen, Foto mit Lupe, Text, Abbrechen
    const pic = this._pic(v);
    return `<div class="card">${pic ? `<img class="bpic" src="${this._esc(pic)}" alt="">` : ""}${v.plate ? `<div class="bplate">${this._plate(v)}</div>` : ""}${shot ? `<div class="scan"><img src="${this._esc(shot)}" alt=""><svg class="lupe" viewBox="0 0 64 64" aria-hidden="true"><circle cx="26" cy="26" r="19" fill="rgba(255,255,255,.28)" stroke="#1b1b1b" stroke-width="5"/><path d="M40 40 L58 58" stroke="#1b1b1b" stroke-width="8" stroke-linecap="round"/><path d="M15 20 A13 13 0 0 1 24 12" stroke="rgba(255,255,255,.9)" stroke-width="3" fill="none" stroke-linecap="round"/></svg></div>` : ""}<div class="brow"><div class="spin"></div><div>${this.T("Beleg wird gelesen …")}${total > 1 ? ` (${i + 1} / ${total})` : ""}</div></div>${strip}<button class="stopb" data-d="stop">${this.T("Abbrechen")}</button></div>`;
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
    const paint = (shot, i) => { busy.innerHTML = this._busyHtml(v, shot, i, total, strip(i)); };
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
    const ents = this._shownIds ? v.entries.filter(x => this._shownIds.has(x.id)) : v.entries;   // gesetzter Filter der Liste
    const rows = [...ents].reverse().map(x => `<tr><td class="n">${pn[x.id] || ""}</td><td>${this._date(x.ts)}</td><td class="n">${x.odometer != null ? this._fmt(x.odometer, 0) : ""}</td><td>${x.kind === "extra" ? "[" + e(x.item || this.T("Zubehör")) + "] " : ""}${e(x.station || "")}<br><small>${e(x.address || "")}</small><br><small>${this._gps(x, false)}</small></td><td class="n">${x.quantity != null ? this._fmt(x.quantity) + " " + (x.kind === "extra" ? e(x.unit || "") : (v.phev && x.energy === "electric" ? "kWh" : u)) : ""}</td><td class="n">${this._fmt(x.unit_price, 3)}</td><td class="n">${this._fmt(x.total)} €</td><td class="n">${x.consumption != null ? this._fmt(x.consumption) : ""}</td><td>${e(x.note || "")}</td></tr>`).join("");
    const photos = ents.filter(x => (x.photo_urls || []).length).map(x => `<div class="g"><div class="c">${this._date(x.ts)} · ${e(x.station || "")} · ${this._fmt(x.total)} €</div>${x.photo_urls.slice(0, 4).map(p => `<img src="${new URL(p, location.origin).href}">`).join("")}</div>`).join("");
    const abs = u => new URL(u, location.origin).href;   // im Druck-Frame brauchen Bilder absolute Adressen
    const logo = abs("/drive_energy_doc_static/icon.png");   // Logo Drive Energy Doc
    const carImg = this._pic(v) ? abs(this._pic(v)) : "";   // Bild des Autos wie im Kopf des Panels
    const plateImg = v.plate ? abs(`/api/drive_energy_doc/plate.svg?cc=${encodeURIComponent(v.plate_country || "DE")}&t=${encodeURIComponent(v.plate)}`) : "";   // das gezeichnete Kennzeichen
    const total = ents.reduce((a, x) => a + (x.total || 0), 0), qty = ents.reduce((a, x) => a + (x.quantity || 0), 0);
    const html = `<!doctype html><meta charset="utf-8"><title>Drive Energy Doc ${e(v.name)}${v.plate ? " " + e(v.plate) : ""}</title><style>
      @page{size:A4 ${orient};margin:${orient === "portrait" ? "10mm" : "12mm"}}body{font:${orient === "portrait" ? "9.5px" : "11px"}/1.35 Arial,sans-serif;color:#000}h1{font-size:16px;margin:0 0 4px}
      table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #bbb;padding:3px 5px;text-align:left;vertical-align:top}
      th{border-bottom:2px solid #000}.n{text-align:right;white-space:nowrap}small{color:#555}
      .g{break-inside:avoid;margin-top:10px}.c{font-weight:bold;margin-bottom:3px}.g img{max-height:75mm;max-width:90mm;margin-right:6px;border:1px solid #ccc}
      h2{margin:14px 0 0;font-size:13px;break-before:page}
      .hd{display:flex;align-items:center;gap:12px;margin-bottom:6px}.hd .logo{height:15mm;width:15mm;flex:none}.hd .tt{flex:1}.hd .plate{height:11mm;width:auto;flex:none}.hd .car{height:16mm;max-width:45mm;object-fit:contain;flex:none}.hd .sub{color:#555;font-size:11px}</style>
      <div class="hd"><img class="logo" src="${logo}" alt="Drive Energy Doc"><div class="tt"><h1>Drive Energy Doc</h1><div class="sub">${e(v.name)}${v.plate ? " · " + e(v.plate) : ""}${this._shownIds ? " · " + this.T("Filter") + ": " + e(this._fltLabel) : ""}</div></div>${carImg ? `<img class="car" src="${e(carImg)}" alt="">` : ""}${plateImg ? `<img class="plate" src="${plateImg}" alt="${e(v.plate)}">` : ""}</div><div>${v.entries.length} ${this.T("Einträge")} · ${this._fmt(qty)} ${u} · ${this._fmt(total)} € · ${this.T("erstellt")} ${new Date().toLocaleDateString(this._locale || "de-DE")}</div>
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
    const isEl = k => k === "electric" || (k === "fuel" && v.energy === "electric");   // Auswahl „Art“ bedeutet Strom (Elektroauto oder Plug-in-Hybrid mit Strom)
    const ctOrig = e && e.charge_type ? e.charge_type : "";
    const estHint = e && e.est_quantity && e.quantity && (e.quantity_source === "beleg" || e.quantity_source === "wallbox") && e.kind !== "extra" ? this.T("Schätzung aus dem Füllstand: {0} {1} (Menge weicht um {2} % ab)", this._fmt(e.est_quantity), (v.phev && e.energy === "electric") || v.energy === "electric" ? "kWh" : this.T(v.unit), (e.quantity / e.est_quantity - 1 >= 0 ? "+" : "") + this._fmt((e.quantity / e.est_quantity - 1) * 100, 1)) : "";
    const gradeCur = e && e.fuel && gradeOpts.includes(e.fuel) ? e.fuel : (gradeOpts.includes(v.energy) ? v.energy : gradeOpts[0]);
    const dlg = document.createElement("div");
    dlg.className = "dlg form";
    dlg.innerHTML = `<div class="card"><div class="bd">
      <div class="dh">${this.T(e ? "Bearbeiten" : "Eintrag von Hand")}${e ? " · " + esc(this._date(e.ts)) : ""}</div>
            <label class="fl"><span>${this.T("Datum")}</span><input id="f_when" type="datetime-local" value="${whenOrig}"></label>
      <div class="g2"><label class="fl"><span>${this.T("Art")}</span><select id="f_kind"><option value="fuel">${esc(v.energy === "electric" ? this.T("Strom") : this.T("Kraftstoff"))}</option>${v.phev ? `<option value="electric"${e && e.kind !== "extra" && e.energy === "electric" ? " selected" : ""}>${esc(this.T("Strom"))}</option>` : ""}${PRESETS.map(x => `<option value="${x.k}"${isExtra && subSel === x.k ? " selected" : ""}>${esc(this.T(x.k))}</option>`).join("")}<option value="other"${isExtra && subSel === "other" ? " selected" : ""}>${esc(this.T("Sonstiges"))}</option></select></label>
      <label class="fl" id="w_grade"${isExtra || v.energy === "electric" || (e && e.energy === "electric") ? ' style="display:none"' : ""}><span>${this.T("Kraftstoffart")}</span><select id="f_grade">${gradeOpts.map(k => `<option value="${k}"${k === gradeCur ? " selected" : ""}>${esc(FUEL_GRADES[k])}</option>`).join("")}</select></label>
      <label class="fl" id="w_ctype"${!isExtra && isEl(e && e.energy === "electric" ? "electric" : "fuel") ? "" : ' style="display:none"'}><span>${this.T("Ladeart")}</span><select id="f_ctype"><option value=""${ctOrig ? "" : " selected"}>${this.T("unbekannt")}</option><option value="ac"${ctOrig === "ac" ? " selected" : ""}>AC</option><option value="dc"${ctOrig === "dc" ? " selected" : ""}>DC</option></select></label></div>
      <div class="g2">${fld("f_item", this.T("Bezeichnung"), e ? e.item || "" : "", ` id="w_item"${isExtra ? "" : ' style="display:none"'}`)}
      ${fld("f_unit", this.T("Einheit"), e ? e.unit : "", ` id="w_unit" title="${esc(this.T("Einheit (z. B. l, Stk), leer = keine"))}"${isExtra ? "" : ' style="display:none"'}`)}</div>
      <div class="g2">
        ${fld("f_q", this.T("Menge"), e ? e.quantity : "")}
        ${curSel ? `<label class="fl"><span>${this.T("Preis")} €</span><div class="pr"><input id="f_p" type="text" inputmode="decimal" value="${esc(e.unit_price)}" autocomplete="off" style="min-width:0"><select id="f_cur" title="${esc(this.T("Währung des Belegs"))}" aria-label="${esc(this.T("Währung des Belegs"))}">${e.orig.currency ? "" : '<option value="" selected>?</option>'}${["EUR", ...CURRENCIES].map(c => `<option value="${c}"${c === e.orig.currency ? " selected" : ""}>${c}</option>`).join("")}</select></div></label>` : fld("f_p", this.T("Preis") + " €", e ? e.unit_price : "")}
        ${fld("f_t", this.T("Betrag") + " €", e ? e.total : "")}
        ${fld("f_km", this.T("Kilometerstand"), e ? e.odometer : "")}
      </div>
      <label class="fl"><span>${this.T("Notiz")}</span><textarea id="f_note" maxlength="1000">${esc(e ? (e.note || this._wbNote(e)) : "")}</textarea></label>${estHint && !this._wbNote(e) ? `<div class="hint">${esc(estHint)}</div>` : ""}
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
    const scan = async files => {   // mehrere Fotos (Säule, Tacho, Beleg): der Reihe nach lesen, die Werte zusammenführen; ein Beleg gilt mehr als ein Display
      for (let i = 0; i < files.length; i++) { if (!(await scanOne(files[i], i, files.length))) break; }
    };
    const scanOne = async (file, i, total) => {   // Foto per KI lesen und die gefundenen Werte in diesen Dialog eintragen (der Dialog bleibt offen); false = Abbruch, nicht weiter
      const btn = dlg.querySelector('[data-d="photo"]');
      btn.disabled = true;
      ph(this.T("Foto wird gelesen …"));
      // derselbe Fortschrittsdialog wie beim Hochladen (Fahrzeugbild, Kennzeichen, Foto mit Lupe, Abbrechen), mitten über dem Dialog
      const busy = document.createElement("div");
      busy.className = "busy";
      const ctl = new AbortController();
      const shotUrl = URL.createObjectURL(file);
      busy.innerHTML = this._busyHtml(v, shotUrl, i, total);
      busy.onclick = ev => { if (ev.target.closest("[data-d=stop]")) ctl.abort(); };
      this.shadowRoot.appendChild(busy);
      let r = null;
      try { r = (await this._upload(v, file, "", "scan", ctl.signal)).scan; } catch (err) {
        busy.remove(); URL.revokeObjectURL(shotUrl); ph(""); btn.disabled = false;
        if (!ctl.signal.aborted) alert(this.T("Fehler") + ": " + (err.message || err));
        return false;
      }
      URL.revokeObjectURL(shotUrl);
      busy.remove();
      btn.disabled = false;
      if (!r) { ph(""); return false; }
      if (r.busy) { ph(""); alert(this.T("Die KI ist gerade überlastet. Bitte in ein paar Minuten noch einmal versuchen.")); return false; }
      if (r.ai_error) { ph(""); alert(this.T("Die gewählte KI hat die Anfrage abgelehnt ({0}). Details stehen im Home-Assistant-Protokoll.", r.ai_error)); return false; }
      if (!r.found) {
        ph("");
        const keep = await ask(this.T("Auf dem Foto konnte ich keine Daten lesen. Soll es trotzdem zur Dokumentation behalten werden?"), this.T("Behalten"), this.T("Verwerfen"));
        if (!keep) { discard([r.photo]); return true; }
        photos.push(r.photo);
        if (!$("f_item").value.trim()) $("f_item").value = this.T("Dokumentation");
        ph(this.T("{0} Foto(s) angehängt", photos.length));
        return true;
      }
      photos.push(r.photo);
      const strong = i === 0 || r.receipt;   // das erste Foto und ein Beleg überschreiben vorhandene Werte, ein späteres Display oder Tacho füllt nur Lücken
      const set = (id, x) => { if (x != null && x !== "" && (strong || !String($(id).value).trim())) $(id).value = x; };
      const cat = { adblue: "AdBlue", oil: "Öl", washer: "Scheibenreiniger", carwash: "Waschen" }[r.category];   // Kategorie aus dem Beleg wählen
      if (!strong) { /* Art und Kraftstoffart bleiben, wie sie sind */ } else if (cat || r.category === "other") {
        $("f_kind").value = cat || "other"; $("f_kind").onchange();
        if (!cat && r.item) $("f_item").value = r.item;
      } else if (r.receipt || r.quantity || r.total) { $("f_kind").value = v.phev && r.category === "charging" ? "electric" : "fuel"; $("f_kind").onchange(); }
      if (strong && r.fuel_grade && gradeOpts.includes(r.fuel_grade)) $("f_grade").value = r.fuel_grade;
      set("f_q", r.quantity); set("f_p", r.unit_price); set("f_t", r.total); set("f_km", r.odometer ? Math.round(r.odometer) : null);
      if (r.note) $("f_note").value = $("f_note").value.trim() ? $("f_note").value.trim() + " · " + r.note : r.note;   // Fremdwährung: Originalpreis und Kurs
      if (r.ts && !e && strong) { const d = new Date(r.ts * 1000); if (!isNaN(d)) $("f_when").value = local(d); }
      ph(this.T("Foto gelesen: Werte eingetragen, bitte prüfen.") + (r.ai_secs != null ? ` (KI ${Math.round(r.ai_secs)} s)` : "") + (photos.length > 1 ? " · " + this.T("{0} Foto(s) angehängt", photos.length) : ""));
      return true;
    };
    const close = () => { if (photos.length) { discard(photos); photos.length = 0; } if (vv && coarse) { vv.removeEventListener("resize", fit); vv.removeEventListener("scroll", fit); } dlg.remove(); this._dlg = null; this._load(); };
    const num = s => (s == null || String(s).trim() === "" ? null : parseFloat(String(s).replace(",", ".")));
    const preset = k => { const m = PRESETS.find(x => x.k === k); if (m) { $("f_item").value = this.T(m.k); $("f_unit").value = m.unit; } };
    $("f_kind").onchange = () => {   // alles außer Kraftstoff/Strom ist Zubehör: Bezeichnung und Einheit, bei den Vorgaben automatisch gefüllt
      const k = $("f_kind").value, x = k !== "fuel" && k !== "electric";
      ["w_item", "w_unit"].forEach(id => { dlg.querySelector("#" + id).style.display = x ? "" : "none"; });
      dlg.querySelector("#w_grade").style.display = x || isEl(k) ? "none" : "";
      dlg.querySelector("#w_ctype").style.display = !x && isEl(k) ? "" : "none";
      if (PRESETS.some(m => m.k === k)) preset(k);
    };
    const save = async () => {
      const f = { quantity: num($("f_q").value), unit_price: num($("f_p").value), total: num($("f_t").value), odometer: num(/^\d{1,3}(\.\d{3})+$/.test($("f_km").value.trim()) ? $("f_km").value.trim().replace(/\./g, "") : $("f_km").value), note: $("f_note").value };
      const extra = $("f_kind").value !== "fuel" && $("f_kind").value !== "electric";
      f.kind = extra ? "extra" : "fuel";
      f.fuel = !extra && $("f_kind").value !== "electric" && v.energy !== "electric" ? $("f_grade").value : "";
      if (!extra && isEl($("f_kind").value) && $("f_ctype").value !== ctOrig) f.charge_type = $("f_ctype").value;   // nur wenn von Hand geändert (sonst bleibt die Quelle Sensor oder Beleg)
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
