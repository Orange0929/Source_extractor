// Run: node tests/test_plot_wheel.cjs (no npm dependencies).
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={ResizeObserver:class{observe(){}},window:{devicePixelRatio:1}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/audio_plot.js'),'utf8')+'\nthis.Plot=AudioPlot',context);
const listeners={};
const viewport={clientWidth:1000,clientHeight:300,scrollLeft:0,addEventListener:(type,fn,opts)=>listeners[type]={fn,opts},getBoundingClientRect:()=>({left:0,top:0})};
const surface={style:{},get clientWidth(){return 1000*parseFloat(this.style.width||100)/100;}};
const plot=new context.Plot({},viewport,surface);plot.draw=()=>{};
vm.runInContext('ViewportBar=class {constructor(){} set(){} }',context);
plot.attachBars({},{});
assert.equal(listeners.wheel.opts.passive,false);assert.equal(listeners.wheel.opts.capture,true);
plot.hBar={set(){},move(delta){plot.horizontal(plot.hStart+delta,plot.hEnd+delta);}};
function wheel(extra){let prevented=false,stopped=false;listeners.wheel.fn({deltaY:-120,deltaX:0,deltaMode:0,clientX:250,clientY:86,preventDefault(){prevented=true},stopPropagation(){stopped=true},...extra});assert.ok(prevented&&stopped);}
// The very first gesture after showing a previously hidden plot must zoom.
plot.viewportReady=false;plot.horizontal(0,1);wheel({ctrlKey:true});
assert.equal(plot.viewportReady,true);assert.ok(plot.hEnd-plot.hStart<1);
plot.horizontal(.2,.8);
const anchor=.2+.25*.6;wheel({ctrlKey:true});assert.ok(plot.hEnd-plot.hStart<.6);assert.ok(Math.abs(plot.hStart+.25*(plot.hEnd-plot.hStart)-anchor)<1e-10);
const pixels=plot.notePixels, note=plot.centerNote+.25*plot.plotHeight()/pixels;
wheel({altKey:true});assert.ok(plot.notePixels>pixels);assert.ok(Math.abs(plot.centerNote+.25*plot.plotHeight()/plot.notePixels-note)<1e-10);
const span=plot.hEnd-plot.hStart,start=plot.hStart,center=plot.centerNote;
wheel({shiftKey:true,deltaY:40});assert.ok(plot.hStart>start);assert.ok(Math.abs(plot.hEnd-plot.hStart-span)<1e-10);assert.equal(plot.centerNote,center);
wheel({deltaY:40});assert.ok(plot.centerNote<center);
for(let i=0;i<100;i++)wheel({ctrlKey:true});assert.ok(plot.hEnd-plot.hStart>=1/40-1e-10);
for(let i=0;i<100;i++)wheel({ctrlKey:true,deltaY:120});assert.equal(plot.hStart,0);assert.equal(plot.hEnd,1);
for(let i=0;i<100;i++)wheel({altKey:true});assert.ok(Math.abs(plot.plotHeight()/plot.notePixels-4)<1e-10);
for(let i=0;i<100;i++)wheel({altKey:true,deltaY:120});assert.ok(Math.abs(plot.plotHeight()/plot.notePixels-128)<1e-10);
console.log('PASS: first Ctrl wheel, Ctrl/Alt anchor zoom, Shift/plain pan, zoom bounds, default zoom cancellation');
