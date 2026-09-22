// Run: node tests/test_editor_transport.cjs (no npm dependencies).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Media extends EventTarget {
  constructor() { super(); this.currentTime=0; this.readyState=1; this.paused=true; this.ended=false; }
  pause() { this.paused=true; }
  load() { this.currentTime=0; this.ended=false; }
  async play() { this.paused=false; this.dispatchEvent(new Event('play')); }
}
(async () => {
  const context={URL,window:{location:{origin:'http://localhost'}},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/editor_transport.js'),'utf8')+'\nthis.Transport=EditorTransport',context);
  const media=new Media(), shown=[], errors=[];
  let loop=true;
  const t=new context.Transport(media,time=>shown.push(time),()=>loop,e=>errors.push(e));
  t.place(550.5);t.prepare('audio',550.5,568,'cursor');await t.play();
  assert.equal(new URL(media.src).searchParams.get('start_s'),'550.500000');
  media.currentTime=2;media.dispatchEvent(new Event('timeupdate'));assert.equal(shown.at(-1),552.5);
  t.stop();assert.equal(shown.at(-1),550.5);assert.equal(media.currentTime,0);
  await t.play();assert.equal(shown.at(-1),550.5);
  // An old queued pause event must not cancel a newly started playback.
  media.dispatchEvent(new Event('pause'));assert.equal(t.active,true);
  media.paused=true;media.dispatchEvent(new Event('pause'));assert.equal(t.active,false);assert.equal(shown.at(-1),550.5);
  // Cursor playback never inherits the selection's repeat checkbox.
  await t.play();media.ended=true;media.paused=true;media.dispatchEvent(new Event('pause'));
  media.dispatchEvent(new Event('ended'));assert.equal(t.active,false);assert.equal(shown.at(-1),550.5);
  t.prepare('audio',552,555,'selection');await t.play();media.ended=true;media.paused=true;
  media.dispatchEvent(new Event('ended'));assert.equal(t.active,true);assert.equal(media.currentTime,0);
  loop=false;media.dispatchEvent(new Event('ended'));assert.equal(t.active,false);
  // Selection edits do not snap an independently placed cursor to their bounds.
  t.place(560);t.prepare('audio',552,555,'selection');assert.equal(t.cursor,560);assert.equal(shown.at(-1),560);
  // Space playback stays inside selection, even with an outside edit cursor.
  loop=false;
  for (const [cursor, expectedStart] of [[550,552],[553,553],[555,552],[560,552]]) {
    t.place(cursor);await t.playSelectionFromCursor('audio',552,555);
    const url=new URL(media.src);
    assert.equal(Number(url.searchParams.get('start_s')),expectedStart);
    assert.equal(Number(url.searchParams.get('end_s')),555);
    media.ended=true;media.paused=true;media.dispatchEvent(new Event('ended'));
    assert.equal(t.active,false);assert.equal(shown.at(-1),cursor);
  }
  // First pass begins at the cursor; following loops cover the full selection.
  loop=true;t.place(553);await t.playSelectionFromCursor('audio',552,555);
  media.ended=true;media.paused=true;media.dispatchEvent(new Event('ended'));
  assert.equal(t.origin,552);assert.equal(t.active,true);
  assert.equal(Number(new URL(media.src).searchParams.get('end_s')),555);
  t.stop();assert.equal(shown.at(-1),553);
  // Stopping while play() is pending must prevent a stale rejection affecting a newer play.
  let reject;
  media.play=()=>new Promise((_,r)=>{reject=r;});
  const pending=t.play();t.stop();reject(new Error('stale'));await pending;assert.equal(errors.length,0);
  media.play=async()=>{throw new Error('decode');};await t.play();assert.equal(t.active,false);assert.equal(errors.length,1);
  console.log('PASS: source time, stop/return, replay, queued pause, cursor vs selection loop, independent selection, cancelled/failed playback');
})();
