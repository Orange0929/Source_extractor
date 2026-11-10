const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let dialog,requests=0,finishRequest;
function element(){return {value:'',listeners:{},style:{},disabled:false,addEventListener(k,fn){this.listeners[k]=fn;},focus(){},click(){if(!this.disabled)this.onclick?.();}};}
const context={window:{},document:{createElement(){
 const children=Object.fromEntries(['textarea','.save','.cancel','.status','.original','.restore'].map(k=>[k,element()]));
 dialog={...element(),children,querySelector:k=>children[k],showModal(){},remove(){},close(){this.listeners.close();}};
 return dialog;
},body:{appendChild(){}}},fetch:()=>{requests++;return new Promise(resolve=>{finishRequest=resolve;});}};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/transcript_editor.js','utf8'),context);
(async()=>{
 let result=context.window.editClipTranscript({id:'a',transcript:'old'});
 const input=dialog.children.textarea;
 function enter(fields={}){let prevented=false;input.listeners.keydown({key:'Enter',preventDefault(){prevented=true;},...fields});return prevented;}
 assert.equal(enter({isComposing:true}),false);assert.equal(enter({keyCode:229}),false);
 assert.equal(enter({shiftKey:true}),false);assert.equal(requests,0);
 assert.equal(enter({repeat:true}),true);assert.equal(requests,0);
 input.value='new';assert.equal(enter(),true);assert.equal(requests,1);
 enter();assert.equal(requests,1,'busy Enter cannot submit twice');
 finishRequest({ok:true,json:async()=>({clip:{transcript:'new'}})});assert.equal(await result,true);
 result=context.window.editClipTranscript({id:'b',transcript:'button'});
 dialog.children['.save'].click();assert.equal(requests,2,'save button still works');
 finishRequest({ok:true,json:async()=>({clip:{transcript:'button'}})});assert.equal(await result,true);
 console.log('Enter save, Shift+Enter newline, IME protection and duplicate-submit checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
