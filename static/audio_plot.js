// Draw only the visible viewport, preserving detail at any horizontal zoom.
class AudioPlot {
  constructor(canvas, viewport, surface) {
    this.canvas = canvas; this.viewport = viewport; this.surface = surface;
    this.data = null; this.points = []; this.gain = 1;
    viewport.addEventListener('scroll', () => this.draw());
    new ResizeObserver(() => this.draw()).observe(viewport);
  }
  clear() { this.data = null; this.points = []; this.draw(); }
  note(midi) {
    const n = Math.round(midi);
    return ['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'][((n % 12) + 12) % 12] + (Math.floor(n / 12) - 1);
  }
  draw() {
    const w = this.viewport.clientWidth;
    if (!w) return;
    const h = 390, dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = w * dpr; this.canvas.height = h * dpr;
    this.canvas.style.width = w + 'px'; this.canvas.style.height = h + 'px';
    const c = this.canvas.getContext('2d'); c.scale(dpr, dpr);
    c.fillStyle = '#0d1420'; c.fillRect(0, 0, w, h);
    if (!this.data) return;
    const {start, end, peaks, rms, gain} = this.data;
    const full = this.surface.clientWidth, offset = this.viewport.scrollLeft;
    const x = t => (t - start) / (end - start) * full - offset;
    const a = start + offset / full * (end - start);
    const span = w / full * (end - start);
    const target = span / 6;
    const power = 10 ** Math.floor(Math.log10(Math.max(target, .001)));
    const step = [1,2,5,10].map(v => v * power).find(v => v >= target);
    c.font = '11px system-ui';
    for (let t = Math.ceil(a / step) * step; t <= Math.min(end, a + span); t += step) {
      const px = x(t);
      c.strokeStyle = '#263244'; c.beginPath(); c.moveTo(px, 22); c.lineTo(px, 365); c.stroke();
      c.fillStyle = '#bac9dc'; c.fillText(t.toFixed(step < 1 ? 2 : 1) + 's', Math.min(w - 52, Math.max(2, px + 4)), 382);
    }
    const band = (values, color) => {
      const amplitudes = [];
      for (let px = 0; px <= w; px++) {
        const first = Math.max(0, Math.floor((offset + px) / full * values.length));
        const last = Math.min(values.length, Math.max(first + 1, Math.ceil((offset + px + 1) / full * values.length)));
        let peak = 0;
        for (let i = first; i < last; i++) peak = Math.max(peak, values[i]);
        amplitudes.push(Math.min(1, peak * gain * this.gain) * 77);
      }
      c.fillStyle = color; c.beginPath();
      amplitudes.forEach((v, i) => i ? c.lineTo(i, 106-v) : c.moveTo(i, 106-v));
      for (let i = amplitudes.length-1; i >= 0; i--) c.lineTo(i, 106+amplitudes[i]);
      c.closePath(); c.fill();
    };
    band(peaks, '#63bddb'); band(rms, '#c3f3ff');
    c.fillStyle = '#c3d3e6'; c.fillText('음량 파형', 8, 17);
    c.fillText('피치 · 음높이', 8, 211);
    const notes = this.points.filter(p => p[1] != null).map(p => 69 + 12 * Math.log2(p[1] / 440));
    let low = notes.length ? Math.floor(Math.min(...notes)) - 2 : 48;
    let high = notes.length ? Math.ceil(Math.max(...notes)) + 2 : 72;
    if (high-low < 12) { const mid=(low+high)/2; low=mid-6; high=mid+6; }
    const y = n => 352 - (n-low)/(high-low)*125;
    const stride = Math.max(1, Math.ceil((high-low)/8));
    for (let n = Math.ceil(low); n <= high; n += stride) {
      c.strokeStyle='#2d3748'; c.beginPath(); c.moveTo(0,y(n)); c.lineTo(w,y(n)); c.stroke();
      c.fillStyle='#c8d1e0'; c.fillText(this.note(n), 5, y(n)-3);
    }
    c.strokeStyle='#ffdb70'; c.lineWidth=2.5; c.lineJoin='round'; c.beginPath();
    let previous = null;
    for (const p of this.points) {
      if (p[1] == null) { previous=null; continue; }
      const n = 69+12*Math.log2(p[1]/440);
      if (!previous || p[0]-previous[0] > .045 || Math.abs(n-previous[1]) > 5) c.moveTo(x(p[0]), y(n));
      else c.lineTo(x(p[0]), y(n));
      previous=[p[0],n];
    }
    c.stroke();
  }
}
