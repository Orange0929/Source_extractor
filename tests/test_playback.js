// Exercise the shipped playback wiring and Space handler without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Media {
  constructor() { this.paused = true; this.listeners = {}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  play() { this.paused = false; for (const fn of this.listeners.play || []) fn(); return Promise.resolve(); }
  pause() { this.paused = true; }
}
const preview = new Media(), source = new Media();
let keydown, prevented = 0;
const context = {
  audioPlayer: preview, sourceAudioPlayer: source,
  EditorTransport: class {
    constructor() { this.active = false; }
    stop() { this.active = false; source.pause(); }
    playSelectionFromCursor() { this.active = true; source.play(); }
  },
  showEditorIndicator() {}, loopSelection: {checked:false}, waveformStatus: {},
  editorAudioId: 'audio', selectionStart: 0, selectionEnd: 1,
  audioPlot: {data: {}}, editorViewStart: 0, editorViewEnd: 1,
  clipEditor: {isConnected:true, style:{}, classList:{contains:()=>false}, contains:()=>false},
  document: {addEventListener:(name,fn)=>{assert.equal(name,'keydown');keydown=fn;}}
};
const app = fs.readFileSync('static/app.js','utf8');
vm.runInNewContext(app.slice(app.indexOf('const editorTransport ='),app.indexOf('function waitForMediaMetadata')),context);
function space({input=false,repeat=false}={}) {
  keydown({code:'Space', target:{closest:selector=>input && selector.includes('input')}, repeat,
    preventDefault:()=>prevented++});
}
preview.play(); space();
assert.equal(preview.paused,true,'first Space stops the row preview');
assert.equal(source.paused,true,'first Space must not start a second player');
space(); assert.equal(source.paused,false,'next Space starts editor playback');
space(); assert.equal(source.paused,true,'following Space stops editor playback');
source.play(); preview.play(); assert.equal(source.paused,true,'row preview stops editor playback');
source.play(); assert.equal(preview.paused,true,'editor/native play stops preview');
source.pause(); context.audioPlot.data=null; preview.play(); space();
assert.equal(preview.paused,true,'preview stops even while waveform is loading');
preview.play(); space({input:true}); assert.equal(preview.paused,false,'typing Space leaves playback alone');
space({repeat:true}); assert.equal(preview.paused,false,'held Space does not toggle repeatedly');
assert.ok(prevented>=5);
console.log('Playback regression checks passed');
