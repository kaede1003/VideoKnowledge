const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs');
const path=require('path');
const ext=path.join(__dirname,'../extension');
const read=f=>fs.readFileSync(path.join(ext,f),'utf8');

test('LoRA module is optional and uses user-initiated local tab capture',()=>{
 const m=JSON.parse(read('manifest.json'));
 assert.equal(m.version,'0.10.0');
 for(const p of ['tabCapture','offscreen','downloads'])assert.ok(m.permissions.includes(p));
 assert.ok(read('offscreen.js').includes('videoPreview.srcObject'));
 assert.ok(read('offscreen.js').includes("toDataURL('image/jpeg'"));
 assert.ok(read('offscreen.js').includes("ws://127.0.0.1:8765/lora/stream/"));
 assert.ok(read('content.js').includes('VKN_LORA_PLAN'));
 assert.ok(read('content.js').includes('VKN_LORA_START'));
 assert.ok(read('content.js').includes('VKN_LORA_EXPORT'));
 assert.ok(read('content.js').includes('训练使用授权'));
});

test('existing ASR still shares the captured stream',()=>{
 assert.ok(read('offscreen.js').includes('VKN_ASR_ATTACH'));
 assert.ok(read('offscreen.js').includes('source.connect(ctx.destination)'));
 assert.ok(read('background.js').includes("'asr-background.js', 'lora-background.js'"));
});
