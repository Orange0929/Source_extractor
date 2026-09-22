// A viewport thumb: drag its middle to pan, or either end to zoom.
class ViewportBar {
  constructor(element, vertical, minimum, change) {
    this.element = element; this.vertical = vertical; this.minimum = minimum;
    this.change = change; this.start = 0; this.end = 1;
    element.innerHTML = '<div class="viewport-thumb"><span class="viewport-end" data-edge="start" tabindex="0" role="slider"></span><span class="viewport-grip" tabindex="0" role="slider"></span><span class="viewport-end" data-edge="end" tabindex="0" role="slider"></span></div>';
    this.thumb = element.firstElementChild;
    [...this.thumb.children].forEach((part, i) => {
      part.setAttribute('aria-label', element.getAttribute('aria-label') + [' 시작 경계', ' 이동', ' 끝 경계'][i]);
      part.setAttribute('aria-orientation', vertical ? 'vertical' : 'horizontal');
      part.setAttribute('aria-valuemin', '0'); part.setAttribute('aria-valuemax', '100');
    });
    element.addEventListener('pointerdown', ev => {
      if (ev.button !== 0) return;
      ev.preventDefault(); ev.stopPropagation();
      const rect = element.getBoundingClientRect();
      const size = vertical ? rect.height : rect.width;
      if (!size) return;
      const position = vertical ? ev.clientY : ev.clientX;
      const edge = ev.target.dataset.edge || 'pan';
      if (!this.thumb.contains(ev.target)) {
        const at = (position - (vertical ? rect.top : rect.left)) / size;
        this.move(at - (this.start + this.end) / 2, 'pan');
      }
      this.drag = {position, size, edge, start: this.start, end: this.end};
      element.setPointerCapture(ev.pointerId);
    });
    element.addEventListener('pointermove', ev => {
      if (!this.drag) return;
      const d = this.drag;
      this.move(((vertical ? ev.clientY : ev.clientX) - d.position) / d.size, d.edge, d.start, d.end);
    });
    const finish = ev => {
      this.drag = null;
      if (element.hasPointerCapture(ev.pointerId)) element.releasePointerCapture(ev.pointerId);
    };
    element.addEventListener('pointerup', finish);
    element.addEventListener('pointercancel', finish);
    element.addEventListener('lostpointercapture', () => { this.drag = null; });
    element.addEventListener('keydown', ev => {
      const direction = {ArrowLeft:-1, ArrowUp:-1, ArrowRight:1, ArrowDown:1}[ev.key];
      if (!direction) return;
      ev.preventDefault(); this.move(direction * (ev.shiftKey ? .05 : .005), ev.target.dataset.edge || 'pan');
    });
    this.set(0, 1);
  }
  move(delta, edge, start = this.start, end = this.end) {
    if (edge === 'start') start = Math.max(0, Math.min(end-this.minimum, start+delta));
    else if (edge === 'end') end = Math.min(1, Math.max(start+this.minimum, end+delta));
    else { delta = Math.max(-start, Math.min(1-end, delta)); start += delta; end += delta; }
    this.set(start, end); this.change(start, end);
  }
  set(start, end) {
    this.start = start; this.end = end;
    this.thumb.style[this.vertical ? 'top' : 'left'] = start*100 + '%';
    this.thumb.style[this.vertical ? 'height' : 'width'] = (end-start)*100 + '%';
    [...this.thumb.children].forEach((part, i) => part.setAttribute('aria-valuenow', ((i === 0 ? start : i === 2 ? end : (start+end)/2)*100).toFixed(1)));
  }
}

// Draw only the visible viewport, preserving detail at any horizontal zoom.
class AudioPlot {
  constructor(canvas, viewport, surface) {
    this.canvas = canvas; this.viewport = viewport; this.surface = surface;
    this.data = null; this.points = []; this.gain = 1;
    this.notePixels = 24; this.centerNote = 60; this.centered = false;
    this.hStart = 0; this.hEnd = 1;
    viewport.addEventListener('scroll', () => { this.syncHorizontal(); this.draw(); });
    new ResizeObserver(() => this.horizontal(this.hStart, this.hEnd)).observe(viewport);
  }
  attachBars(horizontal, vertical) {
    this.hBar = new ViewportBar(horizontal, false, 1/40, (a,b) => this.horizontal(a,b));
    this.vBar = new ViewportBar(vertical, true, 4/128, (a,b) => {
      this.centered = true;
      this.centerNote = 128*(1-(a+b)/2);
      this.notePixels = this.plotHeight()/((b-a)*128);
      this.draw();
    });
    this.viewport.addEventListener('wheel', ev => {
      ev.preventDefault();
      if (ev.shiftKey || Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
        this.hBar.move((ev.deltaX || ev.deltaY) / Math.max(1,this.surface.clientWidth), 'pan');
      } else {
        this.centered = true;
        this.centerNote -= ev.deltaY / this.notePixels;
        this.draw();
      }
    }, {passive:false});
    this.draw();
  }
  plotHeight() { return Math.max(48, this.viewport.clientHeight - 44); }
  syncHorizontal() {
    const full = this.surface.clientWidth;
    if (!full || !this.viewport.clientWidth) return;
    this.hStart = this.viewport.scrollLeft/full;
    this.hEnd = Math.min(1, this.hStart + this.viewport.clientWidth/full);
    if (this.hBar) this.hBar.set(this.hStart, this.hEnd);
  }
  horizontal(start, end) {
    this.hStart = start; this.hEnd = end;
    this.surface.style.width = (100/Math.max(1/40,end-start)) + '%';
    this.viewport.scrollLeft = start*this.surface.clientWidth;
    this.syncHorizontal(); this.draw();
  }
  setPoints(points) {
    this.points = points;
    if (!this.centered) {
      const notes = points.filter(p => p[1] > 0).map(p => 69+12*Math.log2(p[1]/440)).sort((a,b)=>a-b);
      if (notes.length) this.centerNote = notes[Math.floor(notes.length/2)];
      this.centered = true;
    }
    this.draw();
  }
  clear() {
    this.data = null; this.points = []; this.notePixels = 24;
    this.centerNote = 60; this.centered = false; this.horizontal(0,1);
  }
  note(midi) {
    const n = Math.round(midi);
    return ['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'][((n % 12) + 12) % 12] + (Math.floor(n / 12) - 1);
  }
  draw() {
    const w = this.viewport.clientWidth;
    if (!w) return;
    const h = this.viewport.clientHeight || 300, dpr = Math.min(window.devicePixelRatio || 1, 2);
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
    const height = this.plotHeight(), middle = 22 + height/2, bottom = 22+height;
    const visibleNotes = Math.min(128, height/this.notePixels);
    this.notePixels = height/visibleNotes;
    this.centerNote = Math.max(visibleNotes/2, Math.min(128-visibleNotes/2, this.centerNote));
    const low = this.centerNote-visibleNotes/2, high = this.centerNote+visibleNotes/2;
    const y = n => middle - (n-this.centerNote)*this.notePixels;
    if (this.vBar) this.vBar.set(1-high/128, 1-low/128);
    // Each horizontal band is one semitone, centered on the pitch line.
    c.save(); c.beginPath(); c.rect(0, 22, w, height); c.clip();
    for (let n = Math.floor(low)-1; n <= Math.ceil(high)+1; n++) {
      const black = [1,3,6,8,10].includes(((n % 12)+12)%12);
      c.fillStyle = black ? '#101722' : '#222e40';
      c.fillRect(0, y(n+.5), w, y(n-.5)-y(n+.5));
    }
    c.restore();
    c.font = '11px system-ui';
    for (let t = Math.ceil(a / step) * step; t <= Math.min(end, a + span); t += step) {
      const px = x(t);
      c.strokeStyle = '#263244'; c.beginPath(); c.moveTo(px, 22); c.lineTo(px, bottom); c.stroke();
      c.fillStyle = '#bac9dc'; c.fillText(t.toFixed(step < 1 ? 2 : 1) + 's', Math.min(w - 52, Math.max(2, px + 4)), h-8);
    }
    const band = (values, color) => {
      const amplitudes = [];
      for (let px = 0; px <= w; px++) {
        const first = Math.max(0, Math.floor((offset + px) / full * values.length));
        const last = Math.min(values.length, Math.max(first + 1, Math.ceil((offset + px + 1) / full * values.length)));
        let peak = 0;
        for (let i = first; i < last; i++) peak = Math.max(peak, values[i]);
        amplitudes.push(Math.min(1, peak * gain * this.gain) * (height/2-7));
      }
      c.fillStyle = color; c.beginPath();
      amplitudes.forEach((v, i) => i ? c.lineTo(i, middle-v) : c.moveTo(i, middle-v));
      for (let i = amplitudes.length-1; i >= 0; i--) c.lineTo(i, middle+amplitudes[i]);
      c.closePath(); c.fill();
    };
    band(peaks, '#63bddb'); band(rms, '#c3f3ff');
    c.fillStyle = '#c3d3e6'; c.fillText('음량 파형 + 피치', 8, 17);
    c.save(); c.beginPath(); c.rect(0,22,w,height); c.clip();
    const stride = Math.max(1, Math.ceil(18/this.notePixels));
    for (let n = Math.ceil(low); n <= high; n += stride) {
      c.strokeStyle='rgba(112,135,165,.24)'; c.beginPath(); c.moveTo(0,y(n)); c.lineTo(w,y(n)); c.stroke();
      c.fillStyle='#101925'; c.fillRect(2, y(n)-14, 30, 14);
      c.fillStyle='#d8e2ef'; c.fillText(this.note(n), 5, y(n)-3);
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
    // Dark under-stroke keeps pitch legible across both light waveform and dark gaps.
    c.strokeStyle='#18202c'; c.lineWidth=5; c.stroke();
    c.strokeStyle='#ffdb70'; c.lineWidth=2.5; c.stroke();
    c.restore();
  }
}
