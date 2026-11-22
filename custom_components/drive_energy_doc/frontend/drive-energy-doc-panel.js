/* Drive-Energy-Doc-Panel: Fahrzeug-Reiter, Tankliste mit Belegfotos, Bearbeiten, CSV-Export */
const COLS = ["date", "km", "station", "qty", "price", "total", "cons", "receipt", "note", "act"];

const VERSION = "0.1.74";

class DriveEnergyDocPanel extends HTMLElement {
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._load();
  }
  set narrow(v) { this._narrow = v; }
  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      // ShadowRoot kennt kein onclick: echten Listener setzen
      this.shadowRoot.addEventListener("click", ev => { if (this._cur) this._click(ev, this._cur); });
      this.shadowRoot.addEventListener("pointerdown", ev => this._rsStart(ev));
      // Beleg beim Darüberfahren vergrößern (Maus/Stift; am Handy gibt es den Foto-Viewer per Tipp)
      this.shadowRoot.addEventListener("pointerover", ev => {
        const t = ev.target;
        if (ev.pointerType !== "touch" && t.dataset && t.dataset.multi) this._selShow(t);
        else if (ev.pointerType !== "touch" && t.classList && t.classList.contains("thumb")) this._pvShow(t, ev);
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
          try { localStorage.removeItem("deCo"); } catch (e) { /* ignore */ }
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
    this._cw = {};
    this._co = null;
    try { this._co = JSON.parse(localStorage.getItem("deCo") || "null"); } catch (e) { /* ignore */ }
    try { this._cw = JSON.parse(localStorage.getItem("deCw") || "{}") || {}; } catch (e) { /* ignore */ }
    this._ori = "landscape";
    this._rcp = true;
    try { if (localStorage.getItem("deRcp") === "0") this._rcp = false; } catch (e) { /* ignore */ }
    try { if (localStorage.getItem("deOri") === "portrait") this._ori = "portrait"; } catch (e) { /* ignore */ }
    this._render();
    this._timer = setInterval(() => this._load(), 60000);
  }
  disconnectedCallback() { clearInterval(this._timer); }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: "drive_energy_doc/list" });
      if (!this._dlg) this._render();
    } catch (e) { this._err = String(e.message || e); this._render(); }
  }
  _fmt(n, d = 2) { return n == null ? "–" : Number(n).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  _date(ts) { return new Date(ts * 1000).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }); }
  _gps(e, link = true) {
    if (e.lat == null || e.lon == null) return "";
    const txt = `${Number(e.lat).toFixed(5)}, ${Number(e.lon).toFixed(5)}`;
    return link ? `<a href="https://www.google.com/maps/search/?api=1&query=${e.lat},${e.lon}" target="_blank" rel="noopener">${txt}</a>` : txt;
  }
  _order() {
    // gespeicherte Reihenfolge, falls sie genau die bekannten Spalten enthält; „act“ (Knöpfe) bleibt immer ganz rechts
    const o = Array.isArray(this._co) ? this._co.filter(c => COLS.includes(c) && c !== "act") : [];
    COLS.filter(c => c !== "act").forEach(c => { if (!o.includes(c)) o.push(c); });
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
    pop.innerHTML = (e.photo_urls || []).map((p, i) => `<img src="${p}" data-p="${p}" data-entry="${e.id}" data-name="${this._esc((e.photos || [])[i] || "")}" alt="Foto ${i + 1}" title="Foto ${i + 1}">`).join("");
    pop.style.cssText = `position:fixed;z-index:98;padding:8px;border-radius:8px;background:var(--card-background-color);box-shadow:0 2px 12px #0006;border:1px solid var(--divider-color);top:${Math.min(r.bottom - 2, window.innerHeight - 90)}px;left:${Math.max(8, Math.min(r.left - 20, window.innerWidth - 380))}px`;
    pop.addEventListener("pointerleave", ev => { if (ev.pointerType !== "touch") pop.remove(); });
    this._pvHide();
    this.shadowRoot.append(pop);
  }

  _pvHide() {
    if (this._pvEl) { this._pvEl.remove(); this._pvEl = null; }
  }

  async _openPlate(v) {
    // Land und Kennzeichen wählen: Länderliste mit echt gezeichneten Schildern, das große Schild oben zeichnet sich sofort neu
    if (!this._countries) {
      try { this._countries = await this._hass.callWS({ type: "drive_energy_doc/countries" }); }
      catch (e) { alert("Länderliste nicht verfügbar: " + (e.message || e)); return; }
    }
    this._pvHide();
    const st = { cc: v.plate_country || "DE", plate: v.plate || "", q: "" };
    const url = (cc, t) => `/api/drive_energy_doc/plate.svg?cc=${cc}&t=${encodeURIComponent(t)}`;
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.innerHTML = `<div class="card">
      <div class="dh">Kennzeichen · ${this._esc(v.name)}</div>
      <img class="pvp" alt="Vorschau">
      <input id="plt" type="text" maxlength="14" placeholder="Kennzeichen" autocomplete="off" spellcheck="false">
      <input id="cf" type="search" placeholder="Land suchen" autocomplete="off">
      <div class="cl"></div>
      <div class="df"><button data-d="cancel">Abbrechen</button><button data-d="save" class="pri">Speichern</button></div></div>`;
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
        catch (e) { alert("Speichern fehlgeschlagen: " + (e.message || e)); return; }
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
      tbl.style.width = COLS.reduce((t, c) => t + (this._cw[c] || 120), 0) + "px";
    };
    apply();
    const mv = e => { this._cw[key] = Math.max(36, Math.round(w0 + e.clientX - x0)); apply(); };
    const up = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
      h.classList.remove("on"); this._saveCw();
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  }

  _title(v) {
    // Überschrift: Fahrzeugtyp (z. B. „BMW X1 xDrive20d“); enthält er den Namen nicht, steht „Name · Typ“
    const n = v.name || "", t = (v.type || "").trim();
    if (!t) return n;
    return t.toLowerCase().includes(n.toLowerCase()) ? t : `${n} · ${t}`;
  }
  _plate(v) {
    // Dasselbe gezeichnete Schild wie in den Dialogen (mit Länderstreifen, Europa-Ring bei EU-Ländern)
    const src = `/api/drive_energy_doc/plate.svg?cc=${encodeURIComponent(v.plate_country || "DE")}&t=${encodeURIComponent(v.plate)}`;
    return `<img class="plateimg" src="${src}" alt="${this._esc(v.plate)}" title="${this._esc(v.plate)}">`;
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
      note: '<path d="M5 4h14v12h-9l-5 4zM8.5 8.5h7M8.5 12h5"/>',
      close: '<path d="M6 6l12 12M18 6L6 18"/>',
      warn: '<path d="M12 4l9 16H3zM12 10v5M12 17.2v.3"/>',
    };
    return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;
  }
  _esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  _render() {
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
      .sum span{font-size:12px;color:var(--secondary-text-color)}
      .wrap{overflow:auto;background:var(--card-background-color);border-radius:10px}
      table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.3}
      th,td{padding:4px 8px;text-align:left;border-bottom:1px solid var(--divider-color);white-space:nowrap}
      td.n,th.n{text-align:right}
      th{position:sticky;top:0;background:var(--card-background-color);font-weight:500}
      .src{font-size:11px;color:var(--secondary-text-color)}
      .tag{display:inline-block;padding:0 7px;border-radius:9px;background:#0ea5e9;color:#fff;font-size:11px;vertical-align:middle}
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
      .dlg input{font:inherit;padding:8px 10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--primary-background-color);color:inherit}
      .cl{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;overflow:auto;max-height:44vh;padding:2px}
      .cty{display:flex;flex-direction:column;align-items:flex-start;gap:4px;padding:8px;border-radius:10px;text-align:left}
      .cty img{height:32px;max-width:100%}
      .cty span{font-size:12px;color:var(--secondary-text-color)}
      .cty.on{outline:2px solid var(--primary-color);outline-offset:0}
      .df{display:flex;justify-content:flex-end;gap:8px}
      button.pri{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);border-color:var(--primary-color,#03a9f4)}
      .pv{position:fixed;z-index:98;pointer-events:none;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ccc);border-radius:8px;padding:4px;box-shadow:0 6px 24px rgba(0,0,0,.35);left:0;top:0}
      .pv img{display:block;max-width:min(440px,60vw);max-height:min(72vh,560px);border-radius:4px}
      .rs{position:absolute;top:0;right:-3px;bottom:0;width:8px;cursor:col-resize;user-select:none;touch-action:none;z-index:2}
      .rs::after{content:"";position:absolute;left:3px;top:18%;bottom:18%;width:1px;background:var(--secondary-text-color);opacity:.5}
      .multi{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 4px;margin-left:2px;border-radius:9px;background:var(--primary-color);color:var(--text-primary-color,#fff);font-size:11px;cursor:pointer;vertical-align:middle}
      .sel{display:flex;gap:6px;flex-wrap:wrap;max-width:min(80vw,360px)}.sel img{height:64px;width:64px;object-fit:cover;border-radius:6px;cursor:pointer;border:1px solid var(--divider-color)}
      .rs:hover,.rs.on{background:var(--primary-color);opacity:.45}
      th[draggable=true]{cursor:grab}
      th.dropt{outline:2px dashed var(--primary-color);outline-offset:-2px}
      table.fx{table-layout:fixed}
      table.fx td,table.fx th{overflow:hidden;text-overflow:ellipsis}
      .bar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}
      .tm{display:block;color:var(--secondary-text-color);font-size:12px}
      td[data-c=station] .src{display:inline}td[data-c=station] .src.gps{margin-left:8px}
      td[data-c=act] button{padding:3px 7px}td[data-c=act] .ico{width:18px;height:18px}
      .notei{display:inline-flex;cursor:pointer;opacity:.8}.notei:hover{opacity:1}.notei .ico{width:20px;height:20px}
      @media(max-width:700px){
        :host{padding:8px}
        .head{gap:8px}
        .sum{gap:6px;margin-bottom:8px}.sum div{flex:1 1 40%;min-width:0;padding:6px 10px}.sum b{font-size:16px}
        .bar{margin-bottom:8px}
        .wrap{background:none;overflow:visible}
        table,table.fx{display:block;width:100%!important}
        colgroup,thead{display:none}
        tbody{display:block}
        tr{display:grid;grid-template-columns:64px 1fr auto auto;justify-content:stretch;align-items:center;gap:1px 10px;margin-bottom:6px;padding:7px 10px;background:var(--card-background-color);border-radius:10px;
           grid-template-areas:"date station station total" "qty price km cons" "receipt note act act"}
        td,td.n{display:block;padding:0;border:0;white-space:normal;text-align:left;overflow:visible!important;text-overflow:clip!important;min-width:0}
        td:empty{display:none}
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
    if (!d.length) { this.shadowRoot.innerHTML = `<style>${css}</style><h1>Drive Energy Doc</h1><p>Noch kein Fahrzeug. Einstellungen → Geräte &amp; Dienste → Integration „Drive Energy Doc“ hinzufügen.</p>`; return; }
    const s = v.summary, u = v.unit;
    const pic = v.image_url || (v.image && this._hass.states[v.image] ? this._hass.states[v.image].attributes.entity_picture : "");
    const cw = this._cw || {};
    const fixed = COLS.some(c => cw[c]);
    const sumW = COLS.reduce((t, c) => t + (cw[c] || 120), 0);
    const order = this._order();
    const rows = v.entries.map(e => {
      const cell = {
        date: `<td><span>${this._date(e.ts).split(", ")[0]}</span><span class="tm">${this._date(e.ts).split(", ")[1] || ""}</span></td>`,
        km: `<td class="n">${e.odometer != null ? this._fmt(e.odometer, 0) : "–"}</td>`,
        station: `<td><div>${e.kind === "extra" ? `<span class="tag">${this._esc(e.item || "Zubehör")}</span> ` : ""}${this._esc(e.station || "")}</div><div class="src">${this._esc(e.address || "")}</div><div class="src gps">${this._gps(e)}</div></td>`,
        qty: `<td class="n">${e.quantity != null ? this._fmt(e.quantity) + " " + (e.kind === "extra" ? (e.unit || "") : u) : "–"}<div class="src">${e.level_from != null && e.level_to != null ? Math.round(e.level_from) + "→" + Math.round(e.level_to) + " %" : (e.increase != null ? "+" + Math.round(e.increase) + " %" : "")} ${this._esc(e.quantity_source || "")}</div></td>`,
        price: `<td class="n">${this._fmt(e.unit_price, 3)}<div class="src">${this._esc(e.price_source || "")}</div></td>`,
        total: `<td class="n">${this._fmt(e.total)} €</td>`,
        cons: `<td class="n">${e.consumption != null ? this._fmt(e.consumption) : "–"}</td>`,
        receipt: (() => { const ph = e.photo_urls || [], im = (p, k) => `<img class="${k}" src="${p}" data-p="${p}" data-entry="${e.id}" data-name="${this._esc((e.photos || [])[ph.indexOf(p)] || "")}"${ph.length > 1 && k === "thumb" ? ` data-multi="${e.id}"` : ""} alt="${ph.indexOf(p) === 0 && e.receipt ? "Beleg" : "Zusatzfoto"}">`; return `<td>${ph.length ? im(ph[0], "thumb") : ""}${e.receipt ? "" : `<span class="no" title="Beleg fehlt">${this._ico("warn")}</span>`}</td>`; })(),
        note: `<td>${e.note ? `<span class="notei" data-note="${this._esc(e.note)}" title="${this._esc(e.note)}" tabindex="0" role="button" aria-label="Notiz anzeigen">${this._ico("note")}</span>` : ""}</td>`,
        act: `<td><button data-act="photo" title="Foto zu diesem Eintrag" aria-label="Foto hinzufügen">${this._ico("camera")}</button> <button data-act="edit" title="Bearbeiten" aria-label="Bearbeiten">${this._ico("edit")}</button> <button data-act="del" title="Eintrag löschen" aria-label="Eintrag löschen">${this._ico("trash")}</button></td>`,
      };
      return `<tr data-id="${e.id}">${order.map(k => cell[k].replace("<td", `<td data-c="${k}"`)).join("")}</tr>`;
    }).join("");
    this.shadowRoot.innerHTML = `<style>${css}</style>
      <div class="head"><div class="ttl"><img class="logo" src="/drive_energy_doc_static/icon.png?v=${VERSION}" alt=""><div><div class="app">Drive Energy Doc</div><h1>${this._esc(this._title(v))}</h1></div>${v.plate ? this._plate(v) : ""}</div>${pic ? `<img class="car" src="${pic}" alt="${this._esc(v.name)}">` : ""}</div>
      ${d.length > 1 ? `<div class="tabs">${d.map((x, i) => `<button class="${i === this._tab ? "on" : ""}" data-tab="${i}">${this._esc(x.name)}${x.plate ? " · " + this._esc(x.plate) : ""}</button>`).join("")}</div>` : ""}
      <div class="sum">
        <div><b>${s.count}</b><span>Einträge</span></div>
        <div><b>${this._fmt(s.avg_consumption)}</b><span>${u}/100 km (Ø letzte 5)</span></div>
        <div><b>${this._fmt(s.cost_12m)} €</b><span>Kosten 12 Monate</span></div>
        <div><b>${{ idle: "Bereit", candidate: "Anstieg erkannt", refuelling: "Tankt" }[s.status]}</b><span>Status</span></div>
      </div>
      <div class="bar"><button data-act="csv" title="CSV-Export" aria-label="CSV-Export">${this._ico("csv")}</button><button data-act="print" title="Drucken / PDF" aria-label="Drucken">${this._ico("print")}</button><button data-act="ori" title="${this._ori === "portrait" ? "Hochformat" : "Querformat"} (zum Wechseln klicken)" aria-label="Seitenformat">${this._ico(this._ori)}</button><button data-act="rcp" title="Belege im Druck: ${this._rcp ? "mit" : "ohne"} (zum Wechseln klicken)" aria-label="Belege im Druck" aria-pressed="${this._rcp}">${this._ico(this._rcp ? "photo" : "photoOff")}</button><button data-act="plate" title="Kennzeichen und Land ändern" aria-label="Kennzeichen">${this._ico("plate")}</button><button data-act="add" title="Eintrag von Hand hinzufügen" aria-label="Eintrag von Hand">${this._ico("plus")}</button><button data-act="shoot" title="Beleg fotografieren oder hochladen" aria-label="Beleg fotografieren">${this._ico("camera")}</button><input type="file" id="cam" accept="image/*" capture="environment" hidden><input type="file" id="pic" accept="image/*" hidden></div>
      <div class="wrap"><table class="${fixed ? "fx" : ""}" ${fixed ? `style="width:${sumW}px"` : ""}><colgroup>${order.map(c => `<col data-c="${c}" ${cw[c] ? `style="width:${cw[c]}px"` : ""}>`).join("")}</colgroup><thead><tr>${order.map(c => { const H = { date: ["Datum", ""], km: ["km", "n"], station: ["Tankstelle", ""], qty: ["Menge", "n"], price: [`€/${u}`, "n"], total: ["Betrag", "n"], cons: [`${u}/100 km`, "n"], receipt: ["Beleg", ""], note: ["Notiz", ""], act: ["", ""] }[c]; return `<th data-c="${c}" class="${H[1]}" ${c === "act" ? "" : `draggable="true" title="Auf eine andere Überschrift ziehen: Reihenfolge ändern"`}>${H[0]}<span class="rs" data-c="${c}" title="Ziehen: Spaltenbreite ändern · Doppelklick: Breiten und Reihenfolge zurücksetzen"></span></th>`; }).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="ver">Drive Energy Doc ${VERSION}</div>`;
    this._cur = v;
  }

  async _click(ev, v) {
    this._pvHide();
    const old = this.shadowRoot.querySelector(".pop"); if (old) old.remove();
    const t = ev.target.closest ? (ev.target.closest("button,[data-p],[data-tab],[data-note],[data-multi]") || ev.target) : ev.target;
    if (t.dataset.multi) { this._selShow(t); return; }
    if (t.dataset.note) {
      const r = t.getBoundingClientRect(), pop = document.createElement("div");
      pop.className = "pop"; pop.textContent = t.dataset.note;
      pop.style.cssText = `position:fixed;z-index:98;max-width:min(80vw,320px);padding:8px 12px;border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);box-shadow:0 2px 12px #0006;border:1px solid var(--divider-color);font-size:13px;white-space:pre-wrap;top:${r.bottom + 6}px;left:${Math.max(8, Math.min(r.left, window.innerWidth - 328))}px`;
      this.shadowRoot.append(pop);
      return;
    }  // Klick kann auf dem Symbol im Knopf landen
    if (t.dataset.tab != null) { this._tab = +t.dataset.tab; return this._render(); }
    if (t.dataset.p) {
      const lb = document.createElement("div");
      lb.className = "lb";
      lb.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;gap:10px"><img src="${t.dataset.p}" style="max-width:92vw;max-height:80vh"><div><button data-lbact="del" title="Beleg löschen">${this._ico("trash")}Beleg löschen</button> <button data-lbact="close" title="Schließen">${this._ico("close")}Schließen</button></div></div>`;
      lb.style.cssText = "position:fixed;inset:0;background:#000d;display:flex;align-items:center;justify-content:center;z-index:99";
      lb.onclick = async ev => {
        const lbb = ev.target.closest ? ev.target.closest("[data-lbact]") : null;
        const a = lbb ? lbb.dataset.lbact : undefined;
        if (a === "del") {
          if (!confirm("Dieses Foto endgültig löschen (auch das gesicherte Original)?")) return;
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
    if (act === "shoot") return this._pick(v, null);
    if (act === "photo") return this._pick(v, v.entries.find(x => x.id === t.closest("tr").dataset.id));
    const id = t.closest("tr").dataset.id;
    const e = v.entries.find(x => x.id === id);
    if (act === "del") {
      if (confirm(`Eintrag vom ${this._date(e.ts)} endgültig löschen?`)) { await this._hass.callWS({ type: "drive_energy_doc/delete", vehicle: v.id, entry: id }); this._load(); }
    } else if (act === "edit") this._form(v, e);
  }

  _pick(v, entry) {
    // Handy: Kamera direkt; Desktop: Dateiauswahl. Mit Eintrag = Zusatzfoto zu genau diesem Tankvorgang.
    const input = this.shadowRoot.getElementById(window.matchMedia("(pointer:coarse)").matches ? "cam" : "pic");
    input.value = "";
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      let caption = "";
      if (entry) {
        const dt = new Date(entry.ts * 1000);
        caption = `+ ${dt.getDate()}.${dt.getMonth() + 1}.${dt.getFullYear()}`;
      }
      await this._send(v, file, caption);
    };
    input.click();
  }

  async _send(v, file, text) {
    const fd = new FormData();
    if (file) fd.append("file", file, file.name || "beleg.jpg");
    fd.append("text", text || "");
    try {
      const r = await this._hass.fetchWithAuth(`/api/drive_energy_doc/upload/${v.id}`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(`Fehler ${r.status}`);
      const j = await r.json();
      const msg = (j.replies || []).join("\n\n") || "Gespeichert.";
      if (j.awaiting) {
        const ans = prompt(msg + "\n\nAntwort (Datum z. B. 27.10. oder „neu“):");
        if (ans) return this._send(v, null, ans);
      } else alert(msg);
    } catch (e) { alert("Upload fehlgeschlagen: " + (e.message || e)); }
    this._load();
  }

  _print(v, orient = this._ori) {
    // A4 quer oder hoch; im Druckdialog "Als PDF speichern" wählen. Alle Einträge, darunter die Belegfotos je Eintrag (max. 4).
    const u = v.unit, e = this._esc.bind(this);
    const rows = [...v.entries].reverse().map(x => `<tr><td>${this._date(x.ts)}</td><td class="n">${x.odometer != null ? this._fmt(x.odometer, 0) : ""}</td><td>${x.kind === "extra" ? "[" + e(x.item || "Zubehör") + "] " : ""}${e(x.station || "")}<br><small>${e(x.address || "")}</small><br><small>${this._gps(x, false)}</small></td><td class="n">${x.quantity != null ? this._fmt(x.quantity) + " " + (x.kind === "extra" ? e(x.unit || "") : u) : ""}</td><td class="n">${this._fmt(x.unit_price, 3)}</td><td class="n">${this._fmt(x.total)} €</td><td class="n">${x.consumption != null ? this._fmt(x.consumption) : ""}</td><td>${e(x.note || "")}</td></tr>`).join("");
    const photos = v.entries.filter(x => (x.photo_urls || []).length).map(x => `<div class="g"><div class="c">${this._date(x.ts)} · ${e(x.station || "")} · ${this._fmt(x.total)} €</div>${x.photo_urls.slice(0, 4).map(p => `<img src="${new URL(p, location.origin).href}">`).join("")}</div>`).join("");
    const total = v.entries.reduce((a, x) => a + (x.total || 0), 0), qty = v.entries.reduce((a, x) => a + (x.quantity || 0), 0);
    const html = `<!doctype html><meta charset="utf-8"><title>Drive Energy Doc ${e(v.name)}${v.plate ? " " + e(v.plate) : ""}</title><style>
      @page{size:A4 ${orient};margin:${orient === "portrait" ? "10mm" : "12mm"}}body{font:${orient === "portrait" ? "9.5px" : "11px"}/1.35 Arial,sans-serif;color:#000}h1{font-size:16px;margin:0 0 4px}
      table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #bbb;padding:3px 5px;text-align:left;vertical-align:top}
      th{border-bottom:2px solid #000}.n{text-align:right;white-space:nowrap}small{color:#555}
      .g{break-inside:avoid;margin-top:10px}.c{font-weight:bold;margin-bottom:3px}.g img{max-height:75mm;max-width:90mm;margin-right:6px;border:1px solid #ccc}
      h2{margin:14px 0 0;font-size:13px;break-before:page}</style>
      <h1>Drive Energy Doc ${e(v.name)}${v.plate ? " · " + e(v.plate) : ""}</h1><div>${v.entries.length} Einträge · ${this._fmt(qty)} ${u} · ${this._fmt(total)} € · erstellt ${new Date().toLocaleDateString("de-DE")}</div>
      <table><thead><tr><th>Datum</th><th class="n">km</th><th>Tankstelle</th><th class="n">Menge</th><th class="n">€/${u}</th><th class="n">Betrag</th><th class="n">${u}/100 km</th><th>Notiz</th></tr></thead><tbody>${rows}</tbody></table>
      ${photos && this._rcp ? `<h2>Belege</h2>${photos}` : ""}`;
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

  async _form(v, e, kind) {
    kind = e ? e.kind : kind;
    let item = e && e.kind === "extra" ? e.item || "" : "";
    if (!e) {
      // Neuer Eintrag von Hand: Kraftstoff/Strom oder Zubehör (AdBlue, Öl, Scheibenwischer …)
      const art = prompt("Art: leer lassen = " + (v.energy === "electric" ? "Strom" : "Kraftstoff") + ", sonst Bezeichnung des Zubehörs (z. B. AdBlue, Öl, Scheibenwischer)", "");
      if (art === null) return;
      if (art.trim()) { kind = "extra"; item = art.trim(); }
    }
    const extra = kind === "extra";
    // bewusst schlichte Prompts
    const ask = (label, val) => prompt(label, val ?? "");
    const num = s => (s == null || s.trim() === "" ? null : parseFloat(s.replace(",", ".")));
    const f = {};
    let unit = v.unit;
    if (extra) {
      if (e) { const it = ask("Bezeichnung", item); if (it === null) return; f.item = it.trim() || item; }
      const un = ask("Einheit (z. B. l, Stk), leer = keine", e ? e.unit : (/^(adblue|öl|motoröl|scheibenwasser|frostschutz)$/i.test(item) ? "l" : "")); if (un === null) return;
      f.unit = un.trim(); unit = f.unit;
    }
    const q = ask(`${extra ? (f.item || item) + ": " : ""}Menge${unit ? " (" + unit + ")" : ""}${extra ? ", optional" : ""}`, e?.quantity); if (q === null) return; f.quantity = num(q);
    const p = ask(`Preis €${unit ? "/" + unit : ""}`, e?.unit_price); if (p === null) return; f.unit_price = num(p);
    const t = ask("Betrag €", e?.total); if (t === null) return; f.total = num(t);
    const k = ask("Kilometerstand", e?.odometer); if (k === null) return; f.odometer = num(k);
    const n = ask("Notiz", e?.note); if (n === null) return; f.note = n;
    if (e) await this._hass.callWS({ type: "drive_energy_doc/update", vehicle: v.id, entry: e.id, fields: f });
    else {
      const ds = ask("Datum (TT.MM.JJJJ)", new Date().toLocaleDateString("de-DE")); if (!ds) return;
      const [dd, mm, yy] = ds.split("."); f.ts = new Date(+yy, mm - 1, +dd, 12).getTime() / 1000;
      if (extra) { f.kind = "extra"; f.item = item; }
      await this._hass.callWS({ type: "drive_energy_doc/add", vehicle: v.id, fields: f });
    }
    this._load();
  }
}
if (!customElements.get("drive-energy-doc-panel")) customElements.define("drive-energy-doc-panel", DriveEnergyDocPanel);
