// Selection and edit cursor are independent. All times here are source seconds.
class EditorTransport {
  constructor(media, show, loop, error) {
    this.media = media; this.show = show; this.loop = loop; this.error = error;
    this.cursor = 0; this.origin = 0; this.mode = 'selection';
    this.active = false; this.serial = 0; this.frame = 0;
    media.addEventListener('play', () => {
      if (!media.paused) { this.active = true; this.tick(); }
    });
    media.addEventListener('timeupdate', () => {
      if (this.active) this.show(this.origin + media.currentTime);
    });
    media.addEventListener('pause', () => {
      if (media.paused && !media.ended && this.active) this.stop();
    });
    media.addEventListener('ended', () => {
      if (this.active && this.mode === 'selection' && this.loop()) {
        media.currentTime = 0; this.play();
      } else this.stop();
    });
  }
  tick() {
    cancelAnimationFrame(this.frame);
    if (!this.active) return;
    this.show(this.origin + this.media.currentTime);
    this.frame = requestAnimationFrame(() => this.tick());
  }
  stop() {
    this.serial++; this.active = false;
    cancelAnimationFrame(this.frame);
    this.media.pause();
    if (this.media.readyState > 0) this.media.currentTime = 0;
    this.show(this.cursor);
  }
  place(time) {
    this.stop(); this.cursor = time; this.show(time);
  }
  prepare(audioId, start, end, mode) {
    this.stop(); this.origin = start; this.mode = mode;
    const url = new URL(`/api/audio_range/${encodeURIComponent(audioId)}`, window.location.origin);
    url.searchParams.set('start_s', start.toFixed(6));
    url.searchParams.set('end_s', end.toFixed(6));
    url.searchParams.set('download', 'false');
    this.media.src = url.toString(); this.media.load();
  }
  async play() {
    const serial = ++this.serial;
    this.active = true;
    try { await this.media.play(); }
    catch (e) {
      if (serial !== this.serial) return;
      this.stop();
      if (e.name !== 'AbortError') this.error('재생 실패: ' + e.message);
    }
  }
}
