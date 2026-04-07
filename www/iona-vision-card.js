/**
 * iONA Vision Tools Card
 * Zeigt günstigste Startzeit, Kosten und Steuerelemente für mein Strom Vision.
 * Alle Entities optional – ohne Vision Tools läuft die Kachel nicht.
 */
class IonaVisionCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._rendered = false;
    this._sliderLock = {}; // { entity_id: timeout } – sperrt Update nach Service-Call
  }

  setConfig(c) {
    if (!c.entity_startzeit && !c.entity_kosten && !c.entity_zeitraum) {
      throw new Error('Mindestens entity_startzeit oder entity_zeitraum muss gesetzt sein');
    }
    this._c = c;
    this._rendered = false; // Konfig geändert → neu aufbauen
  }

  set hass(h) {
    this._h = h;
    if (!this._rendered) {
      this._renderFull();
    } else {
      this._updateInfo();
      this._updateSliders();
      this._updateSwitch();
    }
  }

  _st(id) {
    if (!id || !this._h) return null;
    const s = this._h.states[id];
    return (s && s.state !== 'unavailable' && s.state !== 'unknown') ? s : null;
  }

  _fmt(v, d = 1) {
    if (v === null || v === undefined) return '\u2014';
    return v.toLocaleString('de-DE', { maximumFractionDigits: d, minimumFractionDigits: d });
  }

  _fmtTime(iso) {
    if (!iso) return '\u2014';
    try {
      const d = new Date(iso);
      if (isNaN(d)) return '\u2014';
      return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + '\u202fUhr';
    } catch (e) { return '\u2014'; }
  }

  _fmtDay(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d)) return '';
      const dStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      const nStart = new Date(); nStart.setHours(0, 0, 0, 0);
      const diff = Math.round((dStart - nStart) / 86400000);
      if (diff === 0) return 'heute';
      if (diff === 1) return 'morgen';
      if (diff === 2) return '\u00fcbermorgen';
      return d.toLocaleDateString('de-DE', { weekday: 'long' });
    } catch (e) { return ''; }
  }

  _fmtCountdown(iso) {
    if (!iso) return '';
    try {
      const diff = new Date(iso) - Date.now();
      if (diff < 0) return 'bereits gestartet';
      const hh = Math.floor(diff / 3600000);
      const mm = Math.floor((diff % 3600000) / 60000);
      return hh > 0
        ? 'in ' + hh + '\u202fh\u202f' + String(mm).padStart(2, '0') + '\u202fmin'
        : 'in ' + mm + '\u202fmin';
    } catch (e) { return ''; }
  }

  _svc(domain, service, data) {
    if (this._h) this._h.callService(domain, service, data);
  }

  // ---- Inkrementelle Updates (kein re-render) --------------------------------

  _updateInfo() {
    const sr = this.shadowRoot;
    const sSt = this._st(this._c.entity_startzeit);
    const sKo = this._st(this._c.entity_kosten);
    const startIso = sSt ? sSt.state : null;
    const kosten   = sKo ? parseFloat(sKo.state) : null;

    const timeEl = sr.querySelector('#sz-time');
    const dayEl  = sr.querySelector('#sz-day');
    const cdEl   = sr.querySelector('#sz-cd');
    const coEl   = sr.querySelector('#sz-cost');

    if (timeEl) timeEl.textContent = this._fmtTime(startIso);
    if (dayEl)  dayEl.textContent  = this._fmtDay(startIso);
    if (cdEl)   cdEl.textContent   = this._fmtCountdown(startIso);
    if (coEl && kosten !== null && !isNaN(kosten)) {
      const stunden = (sSt && sSt.attributes && sSt.attributes.stunden_block)
        || (sKo && sKo.attributes && sKo.attributes.stunden_block) || '?';
      coEl.textContent = '\u00d8\u202f' + this._fmt(kosten * 100, 2) + '\u202fct/kWh\u202f\u00b7\u202f' + stunden + '\u202fh-Fenster';
    }
  }

  _updateSliders() {
    const sr = this.shadowRoot;
    // Zeitraum-Slider
    if (this._c.entity_zeitraum) {
      const id = this._c.entity_zeitraum;
      if (!this._sliderLock[id]) {
        const s = this._st(id);
        if (s) {
          const input = sr.querySelector('input.sl-input[data-id="' + id + '"]');
          const valEl = sr.querySelector('.sl-val[data-id="' + id + '"]');
          if (input && sr.activeElement !== input) {
            const v  = parseFloat(s.state);
            input.min  = parseFloat(s.attributes.min || input.min);
            input.max  = 8; // Card-Limit
            input.step = 1;
            const vc = Math.min(v, 8);
            if (!isNaN(vc) && parseFloat(input.value) !== vc) {
              input.value = vc;
              if (valEl) valEl.textContent = vc + '\u202fh';
              this._updateSliderFill(input);
            }
          }
        }
      }
    }
    // Vorausschau: Slider-Wert als berechnete Uhrzeit anzeigen
    if (this._c.entity_vorausschau) {
      const id = this._c.entity_vorausschau;
      if (!this._sliderLock[id]) {
        const s = this._st(id);
        if (s) {
          const input = sr.querySelector('input.sl-input[data-id="' + id + '"]');
          const valEl = sr.querySelector('.sl-val[data-id="' + id + '"]');
          const dayEl = sr.querySelector('.sl-day[data-id="' + id + '"]');
          if (input && sr.activeElement !== input) {
            const hours = parseFloat(s.state);
            input.min = 1;
            input.max = 24;
            input.step = 1;
            const vc = Math.max(1, Math.min(24, hours));
            if (!isNaN(vc) && parseFloat(input.value) !== vc) {
              input.value = vc;
              this._updateSliderFill(input);
              const target = new Date(Date.now() + vc * 3600000);
              if (valEl) valEl.textContent = String(target.getHours()).padStart(2,'0') + ':' + String(target.getMinutes()).padStart(2,'0') + '\u202fUhr';
              if (dayEl) {
                if (target.getDate() !== new Date().getDate()) {
                  dayEl.textContent = 'morgen';
                  dayEl.style.display = '';
                } else {
                  dayEl.style.display = 'none';
                }
              }
            }
          }
        }
      }
    }
  }

  _updateSliderFill(input) {
    const mn = parseFloat(input.min), mx = parseFloat(input.max);
    const pct = ((parseFloat(input.value) - mn) / (mx - mn) * 100).toFixed(1);
    input.style.setProperty('--pct', pct + '%');
  }

  _updateSwitch() {
    if (!this._c.entity_nacht) return;
    const s = this._st(this._c.entity_nacht);
    if (!s) return;
    const btn = this.shadowRoot.querySelector('.sw-btn[data-switch="' + this._c.entity_nacht + '"]');
    if (!btn) return;
    if (s.state === 'on') btn.classList.add('sw-on');
    else btn.classList.remove('sw-on');
  }

  // ---- Einmaliger Vollaufbau ------------------------------------------------

  _buildVorausschauSlider(id) {
    const s = this._st(id);
    if (!s) return '';
    const hours = parseFloat(s.state);
    const mn  = 1;
    const mx  = 24;
    const st  = 1;
    const vc  = Math.max(mn, Math.min(mx, hours));
    const pct = ((vc - mn) / (mx - mn) * 100).toFixed(1);
    const target = new Date(Date.now() + vc * 3600000);
    const tv = String(target.getHours()).padStart(2,'0') + ':' + String(target.getMinutes()).padStart(2,'0') + '\u202fUhr';
    const isNext = target.getDate() !== new Date().getDate();
    return '<div class="sl-row">' +
      '<span class="sl-lbl">Sp\u00e4teste<br>Startzeit</span>' +
      '<input type="range" class="sl-input" data-id="' + id + '"' +
        ' min="' + mn + '" max="' + mx + '" step="' + st + '" value="' + vc + '"' +
        ' style="--pct:' + pct + '%">' +
      '<div class="sl-val-col">' +
        '<span class="sl-val" data-id="' + id + '">' + tv + '</span>' +
        '<span class="sl-day" data-id="' + id + '"' + (isNext ? '' : ' style="display:none"') + '>morgen</span>' +
      '</div>' +
    '</div>';
  }

  _buildTimePicker(id) {
    const s = this._st(id);
    if (!s) return '';
    const hours = parseFloat(s.state);
    const mn = parseFloat(s.attributes.min || 1);
    const mx = parseFloat(s.attributes.max || 48);
    const target = new Date(Date.now() + hours * 3600000);
    const tv = String(target.getHours()).padStart(2,'0') + ':' + String(target.getMinutes()).padStart(2,'0');
    const isNext = target.getDate() !== new Date().getDate();
    return '<div class="tp-row">' +
      '<span class="sl-lbl">Späteste<br>Startzeit</span>' +
      '<div class="tp-wrap">' +
        '<span class="tp-day" data-id="' + id + '">' + (isNext ? 'morgen' : 'heute') + '</span>' +
        '<input type="time" class="tp-input" data-id="' + id + '" data-min="' + mn + '" data-max="' + mx + '" value="' + tv + '">' +
      '</div>' +
    '</div>';
  }

  _buildSlider(id, label, overrideMax, overrideStep) {
    const s = this._st(id);
    if (!s) return '';
    const v   = parseFloat(s.state);
    const mn  = parseFloat(s.attributes.min  || 1);
    const mx  = overrideMax  !== undefined ? overrideMax  : parseFloat(s.attributes.max  || 48);
    const st  = overrideStep !== undefined ? overrideStep : parseFloat(s.attributes.step || 1);
    const vc  = Math.min(v, mx);
    const pct = ((vc - mn) / (mx - mn) * 100).toFixed(1);
    return '<div class="sl-row">' +
      '<span class="sl-lbl">' + label + '</span>' +
      '<input type="range" class="sl-input" data-id="' + id + '"' +
        ' min="' + mn + '" max="' + mx + '" step="' + st + '" value="' + vc + '"' +
        ' style="--pct:' + pct + '%">' +
      '<span class="sl-val" data-id="' + id + '">' + vc + '\u202fh</span>' +
    '</div>';
  }

  _buildSwitch(id, label) {
    const s = this._st(id);
    if (!s) return '';
    const on = s.state === 'on';
    return '<div class="sw-row">' +
      '<span class="sw-lbl">' + label + '</span>' +
      '<button class="sw-btn' + (on ? ' sw-on' : '') + '" data-switch="' + id + '">' +
        '<span class="sw-knob"></span>' +
      '</button>' +
    '</div>';
  }

  _renderFull() {
    if (!this._c || !this._h) return;

    const sSt = this._st(this._c.entity_startzeit);
    const sKo = this._st(this._c.entity_kosten);
    const startIso = sSt ? sSt.state : null;
    const kosten   = sKo ? parseFloat(sKo.state) : null;
    const stunden  = (sSt && sSt.attributes && sSt.attributes.stunden_block)
      || (sKo && sKo.attributes && sKo.attributes.stunden_block) || '?';

    const sliderZ = this._c.entity_zeitraum    ? this._buildSlider(this._c.entity_zeitraum,    'Zeitraum', 8, 1)    : '';
    const sliderV = this._c.entity_vorausschau ? this._buildVorausschauSlider(this._c.entity_vorausschau) : '';
    const sw      = this._c.entity_nacht       ? this._buildSwitch(this._c.entity_nacht, 'Nur Nachtstrom (20\u201307\u00a0Uhr)') : '';
    const hasControls = sliderZ || sliderV || sw;

    const mainHtml = (startIso && this._fmtTime(startIso) !== '\u2014')
      ? '<div class="sz-wrap">' +
          '<div class="sz-label">G\u00fcnstigste Startzeit</div>' +
          '<div id="sz-time" class="sz-time">' + this._fmtTime(startIso) + '</div>' +
          '<div class="sz-meta">' +
            '<span id="sz-day" class="sz-day">' + this._fmtDay(startIso) + '</span>' +
            '<span id="sz-cd"  class="sz-cd">'  + this._fmtCountdown(startIso) + '</span>' +
          '</div>' +
          '<div id="sz-cost" class="sz-cost">' +
            (kosten !== null && !isNaN(kosten)
              ? '\u00d8\u202f' + this._fmt(kosten * 100, 2) + '\u202fct/kWh\u202f\u00b7\u202f' + stunden + '\u202fh-Fenster'
              : '') +
          '</div>' +
        '</div>'
      : '<div class="nd">Keine Vision-Daten verf\u00fcgbar</div>';

    this.shadowRoot.innerHTML =
      '<style>' +
        ':host{display:block}' +
        'ha-card{padding:16px 20px 18px}' +
        '.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}' +
        '.ti{font-size:13px;font-weight:500;letter-spacing:.6px;text-transform:uppercase;color:var(--secondary-text-color)}' +
        '.badge{font-size:11px;font-weight:700;padding:2px 9px;border-radius:12px;letter-spacing:.5px;background:#4caf5022;color:#4caf50;border:1px solid #4caf5055}' +
        '.sz-wrap{text-align:center;padding:4px 0 20px}' +
        '.sz-label{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--secondary-text-color);margin-bottom:6px}' +
        '.sz-time{font-size:52px;font-weight:700;color:var(--primary-color);line-height:1}' +
        '.sz-meta{display:flex;justify-content:center;gap:10px;margin-top:5px}' +
        '.sz-day{font-size:13px;font-weight:600;color:var(--primary-text-color)}' +
        '.sz-cd{font-size:12px;color:var(--secondary-text-color)}' +
        '.sz-cost{font-size:13px;color:var(--secondary-text-color);margin-top:8px;min-height:1.4em}' +
        '.dv{height:1px;background:var(--divider-color,rgba(128,128,128,.2));margin:0 0 16px}' +
        '.sl-row{display:flex;align-items:center;gap:10px;margin-bottom:14px}' +
        '.sl-lbl{font-size:12px;color:var(--secondary-text-color);width:80px;flex-shrink:0}' +
        '.sl-input{flex:1;-webkit-appearance:none;appearance:none;height:6px;border-radius:3px;outline:none;cursor:pointer;touch-action:none;' +
          'background:linear-gradient(to right,var(--primary-color) var(--pct,0%), var(--secondary-background-color) var(--pct,0%))}' +
        '.sl-input::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:var(--primary-color);cursor:pointer;box-shadow:0 1px 4px rgba(0,0,0,.35)}' +
        '.sl-input::-moz-range-thumb{width:20px;height:20px;border-radius:50%;background:var(--primary-color);cursor:pointer;border:none;box-shadow:0 1px 4px rgba(0,0,0,.35)}' +
        '.sl-lbl-col{display:flex;flex-direction:column;width:80px;flex-shrink:0}' +
        '.sl-val-col{display:flex;flex-direction:column;align-items:flex-end;width:60px;flex-shrink:0}' +
        '.sl-day{font-size:10px;color:var(--secondary-text-color);margin-top:1px}' +
        '.sl-val{font-size:13px;font-weight:600;color:var(--primary-text-color);text-align:right}' +
        '.sw-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}' +
        '.sw-lbl{font-size:13px;color:var(--primary-text-color)}' +
        '.sw-btn{position:relative;width:40px;height:22px;border-radius:11px;border:none;background:var(--secondary-background-color);cursor:pointer;transition:background .2s;outline:none;padding:0}' +
        '.sw-btn.sw-on{background:var(--primary-color)}' +
        '.sw-knob{position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.3);transition:transform .2s;display:block}' +
        '.sw-btn.sw-on .sw-knob{transform:translateX(18px)}' +
        '.nd{text-align:center;font-size:12px;color:var(--secondary-text-color);padding:24px 0}' +
      '</style>' +
      '<ha-card>' +
        '<div class="hd">' +
          '<span class="ti">\u26a1 Vision Tools</span>' +
          '<span class="badge">enviaM</span>' +
        '</div>' +
        mainHtml +
        (hasControls ? '<div class="dv"></div>' + sliderZ + sliderV + sw : '') +
      '</ha-card>';

    this._attachEvents();
    this._rendered = true;
  }

  _attachEvents() {
    const sr = this.shadowRoot;

    // Native range inputs – live-update der Anzeige + Gradient, Service-Call on change
    sr.querySelectorAll('.sl-input').forEach(input => {
      const isVorausschau = input.dataset.id === (this._c.entity_vorausschau || '');
      const valEl = sr.querySelector('.sl-val[data-id="' + input.dataset.id + '"]');
      const dayEl = sr.querySelector('.sl-day[data-id="' + input.dataset.id + '"]');
      input.addEventListener('input', () => {
        if (isVorausschau) {
          const target = new Date(Date.now() + parseFloat(input.value) * 3600000);
          if (valEl) valEl.textContent = String(target.getHours()).padStart(2,'0') + ':' + String(target.getMinutes()).padStart(2,'0') + '\u202fUhr';
          if (dayEl) {
            if (target.getDate() !== new Date().getDate()) {
              dayEl.textContent = 'morgen';
              dayEl.style.display = '';
            } else {
              dayEl.style.display = 'none';
            }
          }
        } else {
          if (valEl) valEl.textContent = input.value + '\u202fh';
        }
        this._updateSliderFill(input);
      });
      input.addEventListener('change', () => {
        const id = input.dataset.id;
        const val = parseFloat(input.value);
        // Sperre diesen Slider für 8s damit HA-Updates ihn nicht zurücksetzen
        clearTimeout(this._sliderLock[id]);
        this._sliderLock[id] = setTimeout(() => { delete this._sliderLock[id]; }, 8000);
        this._svc('number', 'set_value', { entity_id: id, value: val });
      });
    });

    // Time-Picker-Events entfernt (kein tp-input mehr)

    // Switch
    sr.querySelectorAll('.sw-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const s = this._st(btn.dataset.switch);
        if (!s) return;
        this._svc('switch', s.state === 'on' ? 'turn_off' : 'turn_on', { entity_id: btn.dataset.switch });
        btn.classList.toggle('sw-on');
      });
    });
  }

  getCardSize() { return 4; }

  static getStubConfig() {
    return {
      entity_startzeit:   'sensor.vision_tools_gunstigste_startzeit_fur_2h',
      entity_kosten:      'sensor.vision_tools_durchschnittskosten_fur_die_2h',
      entity_zeitraum:    'number.mein_strom_vision_tools_vision_tools_zeitraum',
      entity_vorausschau: 'number.mein_strom_vision_tools_vision_tools_vorausschau',
      entity_nacht:       'switch.mein_strom_vision_tools_vision_tools_nur_nachtstrom',
    };
  }
}

customElements.define('iona-vision-card', IonaVisionCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'iona-vision-card',
  name: 'iONA Vision Tools',
  description: 'G\u00fcnstigste Startzeit, Durchschnittskosten und Optimierungs-Steuerung f\u00fcr mein Strom Vision.',
  preview: false,
  documentationURL: 'https://github.com/tinohoehne/iona-ha',
});
