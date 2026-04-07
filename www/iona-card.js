/**
 * iONA Stromzähler Card
 * Zeigt Momentanleistung, Zählerstände + optionalen Strompreis-Chart (Vision).
 * entity_price ist optional – ohne Vision läuft die Kachel ohne Preis/Chart.
 */
class IonaCard extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: 'open' }); this._histCache=null;this._histLast=0;this._histFetching=false; }

  setConfig(c) {
    if (!c.entity_power) throw new Error('entity_power muss gesetzt sein');
    this._c = c;
  }

  set hass(h) { this._h = h; this._render(); this._maybeUpdateHistory(); }

  _st(id) {
    if (!id || !this._h) return null;
    const s = this._h.states[id];
    return (s && s.state !== 'unavailable' && s.state !== 'unknown') ? s : null;
  }

  _num(id) {
    const s = this._st(id);
    if (!s) return null;
    const v = parseFloat(s.state);
    return isNaN(v) ? null : v;
  }

  _fmt(v, d = 1) {
    if (v === null) return '\u2014';
    return v.toLocaleString('de-DE', { maximumFractionDigits: d, minimumFractionDigits: d });
  }

  _maybeUpdateHistory() {
    if (this._histFetching) return;
    const now = Date.now();
    if (this._histCache && (now - this._histLast) < 300000) return;
    this._histFetching = true;
    const eid = this._c.entity_power;
    const end = new Date(now).toISOString();
    const s = new Date(now - 86400000).toISOString();
    this._h.callApi('GET',
      'history/period/' + s + '?filter_entity_id=' + eid +
      '&end_time=' + encodeURIComponent(end) +
      '&minimal_response=true&significant_changes_only=false'
    ).then(data => {
      this._histFetching = false;
      if (data && data[0] && data[0].length > 1) {
        this._histCache = data[0];
        this._histLast = Date.now();
        this._render();
      }
    }).catch(() => { this._histFetching = false; });
  }

  _sparkline(hist) {
    const now = Date.now(), s24 = now - 86400000;
    const pts = [];
    for (const e of hist) {
      const v = parseFloat(e.state);
      if (isNaN(v)) continue;
      const ts = new Date(e.last_changed || e.last_updated).getTime();
      if (ts < s24 || ts > now) continue;
      pts.push({ t: ts, v });
    }
    if (pts.length < 2) return '';
    const step = Math.ceil(pts.length / 240);
    const sp = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
    const W = 240, H = 44;
    const tr = now - s24;
    const vs = sp.map(p => p.v);
    const mn = Math.min(...vs), mx = Math.max(...vs), vr = mx - mn || 1;
    const fx = t => ((t - s24) / tr * W);
    const fy = v => H - ((v - mn) / vr * (H * 0.88)) - H * 0.06;
    const coords = sp.map(p => fx(p.t).toFixed(1) + ',' + fy(p.v).toFixed(1)).join(' ');
    const last = sp[sp.length - 1];
    const lx = fx(last.t).toFixed(1), ly = fy(last.v).toFixed(1);
    const f0 = fx(sp[0].t).toFixed(1);
    const fi = last.v < 0;
    const lc = fi ? '#4caf50' : 'var(--primary-color)';
    const hasZ = mn < 0 && mx > 0;
    const zy = fy(0).toFixed(1);
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"' +
      ' style="width:100%;height:44px;display:block">' +
      '<polygon points="' + f0 + ',' + H + ' ' + coords + ' ' + lx + ',' + H + '"' +
      ' fill="' + lc + '" opacity="0.12"/>' +
      (hasZ ? '<line x1="0" y1="' + zy + '" x2="' + W + '" y2="' + zy +
      '" stroke="rgba(128,128,128,.4)" stroke-width=".7" stroke-dasharray="3,3"/>' : '') +
      '<polyline points="' + coords + '" fill="none" stroke="' + lc + '" stroke-width="1.5"' +
      ' stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + lx + '" cy="' + ly + '" r="2.5" fill="' + lc + '"/>' +
      '</svg>' +
      '<div class="sh"><span>-24h</span><span>jetzt</span></div>';
  }

  _chart(spots) {
    // Ab -12h bis zum letzten verfügbaren Datenpunkt (inkl. morgen)
    const now = Date.now();
    const start = now - 12 * 3600 * 1000;
    const hm = {};
    for (const { t, p } of spots) {
      if (t < start) continue;
      const d = new Date(t);
      const hk = d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate() + '-' + d.getHours();
      if (!hm[hk]) {
        hm[hk] = {
          ts: new Date(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours()).getTime(),
          h: d.getHours(), pp: []
        };
      }
      hm[hk].pp.push(p);
    }
    const entries = Object.values(hm)
      .sort((a, b) => a.ts - b.ts)
      .map(e => ({ ts: e.ts, h: e.h, p: e.pp.reduce((a, v) => a + v, 0) / e.pp.length }));

    if (!entries.length) return '<p class="nd">Keine Preisdaten verf\u00fcgbar</p>';

    const pp = entries.map(e => e.p);
    const mn = Math.min(...pp), mx = Math.max(...pp), rng = mx - mn || 1;
    const srt = [...pp].sort((a, b) => a - b);
    const p33 = srt[Math.floor(srt.length * 0.33)];
    const p66 = srt[Math.floor(srt.length * 0.66)];
    const nowH = new Date(now); nowH.setMinutes(0, 0, 0);
    const chTs = nowH.getTime();

    const col = (p, ts) => {
      if (ts === chTs) return 'var(--primary-color)';
      if (p <= p33) return '#4caf50';
      if (p <= p66) return '#ff9800';
      return '#f44336';
    };

    const H = 56, bw = 9, step = 10;
    const VW = entries.length * step;

    const bars = entries.map((e, i) => {
      const bh = Math.max(2, ((e.p - mn) / rng) * H);
      const op = e.ts < chTs ? '0.35' : '1';
      return '<rect x="' + (i * step + 0.5) + '" y="' + (H - bh).toFixed(1) +
        '" width="' + bw + '" height="' + bh.toFixed(1) + '" fill="' + col(e.p, e.ts) +
        '" opacity="' + op + '" rx="1.5"/>';
    }).join('');

    // Jetzt-Linie
    const curIdx = entries.findIndex(e => e.ts === chTs);
    const nowLine = curIdx >= 0
      ? '<line x1="' + (curIdx * step + bw / 2) + '" y1="0"' +
        ' x2="' + (curIdx * step + bw / 2) + '" y2="' + H + '"' +
        ' stroke="var(--primary-color)" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.5"/>'
      : '';

    // Labels bei 0:00 und 12:00
    const lbls = entries.map((e, i) => {
      if (e.h !== 0 && e.h !== 12) return '';
      return '<text x="' + (i * step + bw / 2) + '" y="75" font-size="8"' +
        ' fill="var(--secondary-text-color)" text-anchor="middle">' +
        String(e.h).padStart(2, '0') + ':00</text>';
    }).join('');

    return '<div class="cm"><span>' + (mn / 10).toFixed(1) + ' ct</span>' +
      '<span>ct/kWh ab -12h</span>' +
      '<span>' + (mx / 10).toFixed(1) + ' ct</span></div>' +
      '<svg viewBox="0 0 ' + VW + ' 80" preserveAspectRatio="none"' +
      ' style="width:100%;height:78px;display:block">' +
      nowLine + bars + lbls + '</svg>';
  }

  _render() {
    if (!this._c || !this._h) return;

    const pw = this._num(this._c.entity_power);
    const co = this._num(this._c.entity_consumed);
    const fb = this._num(this._c.entity_fed_back);
    const ss = this._st(this._c.entity_source);
    const stxt = ss ? ss.state : '\u2014';

    const fi = pw !== null && pw < 0;
    const pc = fi ? '#4caf50' : 'var(--primary-color)';
    const pa = fi ? '\u2193' : '\u2191';
    const pl = fi ? 'Einspeisung' : 'Verbrauch';
    const pv = pw !== null ? this._fmt(Math.abs(pw), 0) : '\u2014';
    const sc = stxt === 'LAN' ? '#4caf50' : '#ff9800';

    let priceHtml = '';
    if (this._c.entity_price) {
      const ps = this._st(this._c.entity_price);
      const pn = ps ? parseFloat(ps.state) : null;
      const sp = (ps && ps.attributes && ps.attributes.spot_prices) ? ps.attributes.spot_prices : [];
      if (pn !== null && !isNaN(pn)) {
        const ct = pn * 100;
        const vt = this._fmt(ct, 1) + ' ct/kWh';
        let vc, vb;
        if (ct < 20)      { vc = '#4caf50'; vb = 'g\u00fcnstig'; }
        else if (ct < 30) { vc = '#ff9800'; vb = 'mittel'; }
        else              { vc = '#f44336'; vb = 'teuer'; }
        priceHtml =
          '<div class="dv"></div>' +
          '<div class="pr">' +
            '<span class="pl">Strompreis</span>' +
            '<span class="pval" style="color:' + vc + '">' + vt + '</span>' +
            (vb ? '<span class="pb" style="color:' + vc + ';background:' + vc + '22;border:1px solid ' + vc + '55">' + vb + '</span>' : '') +
          '</div>' +
          (sp.length ? this._chart(sp) : '');
      } else if (sp.length) {
        // Preisentity nicht auflösbar aber Chartdaten vorhanden
        priceHtml = '<div class="dv"></div>' + this._chart(sp);
      }
      // Sonst: Vision inaktiv – priceHtml bleibt leer
    }

    this.shadowRoot.innerHTML =
      '<style>' +
        ':host{display:block}' +
        'ha-card{padding:16px 20px 18px}' +
        '.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}' +
        '.ti{font-size:13px;font-weight:500;letter-spacing:.6px;text-transform:uppercase;color:var(--secondary-text-color)}' +
        '.sb{font-size:11px;font-weight:700;padding:2px 9px;border-radius:12px;background:' + sc + '22;color:' + sc + ';border:1px solid ' + sc + '55;letter-spacing:.5px}' +
        '.pw{display:flex;flex-direction:column;align-items:center;padding:8px 0 10px}' +
        '.pp{font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:' + pc + ';margin-bottom:6px;opacity:.85}' +
        '.pr2{display:flex;align-items:baseline;gap:4px}' +
        '.pn{font-size:52px;font-weight:700;color:' + pc + ';line-height:1}' +
        '.pu{font-size:20px;font-weight:400;color:var(--secondary-text-color);align-self:flex-end;padding-bottom:6px}' +
        '.st{display:grid;grid-template-columns:1fr 1fr;gap:8px}' +
        '.si{background:var(--secondary-background-color);border-radius:12px;padding:10px 12px;text-align:center}' +
        '.sl{font-size:11px;color:var(--secondary-text-color);margin-bottom:5px}' +
        '.sv{font-size:17px;font-weight:600;color:var(--primary-text-color)}' +
        '.su{font-size:11px;color:var(--secondary-text-color);margin-left:2px}' +
        '.ca{color:var(--primary-color)}.fa{color:#4caf50}' +
        '.dv{height:1px;background:var(--divider-color,rgba(128,128,128,.2));margin:16px 0 14px}' +
        '.pr{display:flex;align-items:center;gap:8px;margin-bottom:12px}' +
        '.pl{font-size:12px;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.5px;flex-shrink:0}' +
        '.pval{font-size:20px;font-weight:700;flex:1}' +
        '.pb{font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;letter-spacing:.4px;flex-shrink:0}' +
        '.cm{display:flex;justify-content:space-between;font-size:11px;color:var(--secondary-text-color);margin-bottom:4px}' +
        '.nd{text-align:center;font-size:12px;color:var(--secondary-text-color);margin:8px 0}' +
        '.sh{display:flex;justify-content:space-between;font-size:10px;color:var(--secondary-text-color);padding:0 2px 2px;margin-bottom:10px}' +
      '</style>' +
      '<ha-card>' +
        '<div class="hd">' +
          '<span class="ti">\u26a1 iONA Stromz\u00e4hler</span>' +
          '<span class="sb">' + stxt + '</span>' +
        '</div>' +
        '<div class="pw">' +
          '<div class="pp">' + pa + ' ' + pl + '</div>' +
          '<div class="pr2"><span class="pn">' + pv + '</span><span class="pu">W</span></div>' +
        '</div>' +
        (this._histCache ? this._sparkline(this._histCache) : '') +
        '<div class="st">' +
          '<div class="si"><div class="sl ca">\u25b2 Verbrauch</div><div class="sv">' + this._fmt(co) + '<span class="su">kWh</span></div></div>' +
          '<div class="si"><div class="sl fa">\u25bc Einspeisung</div><div class="sv">' + this._fmt(fb) + '<span class="su">kWh</span></div></div>' +
        '</div>' +
        priceHtml +
      '</ha-card>';
  }

  getCardSize() { return (this._c && this._c.entity_price) ? 5 : 4; }

  static getStubConfig() {
    return {
      entity_power:    'sensor.stromzahler_momentanleistung',
      entity_consumed: 'sensor.stromzahler_gesamtverbrauch',
      entity_fed_back: 'sensor.stromzahler_gesamteinspeisung',
      entity_source:   'sensor.stromzahler_datenquelle',
    };
  }
}

customElements.define('iona-card', IonaCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'iona-card',
  name: 'iONA Stromz\u00e4hler',
  description: 'Echtzeit-Leistung, Z\u00e4hlersst\u00e4nde und optionaler Strompreis-Chart (Vision).',
  preview: false,
  documentationURL: 'https://github.com/tinohoehne/iona-ha',
});
