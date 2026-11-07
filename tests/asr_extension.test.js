const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs');
const path=require('path');
const ext=path.join(__dirname,'../extension');
const read=n=>fs.readFileSync(path.join(ext,n),'utf8');

test('local voice capture is manifested as user-initiated MV3 and all assets exist',()=>{
 const manifest=JSON.parse(read('manifest.json'));
 assert.equal(manifest.version,'0.10.0');
 for(const permission of ['tabCapture','offscreen'])assert.ok(manifest.permissions.includes(permission));
 assert.ok(manifest.host_permissions.includes('http://127.0.0.1/*'));
 for(const name of ['offscreen.html','offscreen.js','audio-processor.js','asr-background.js'])assert.ok(fs.existsSync(path.join(ext,name)));
 assert.ok(read('background.js').includes("chrome.action.onClicked.addListener(vknOnAction)"));
 assert.ok(read('asr-background.js').includes('chrome.tabCapture.getMediaStreamId'));
 assert.ok(read('offscreen.js').includes('source.connect(ctx.destination)'));
});

test('backend is loopback-only and UI exposes local transcript workflow',()=>{
 assert.ok(read('content.js').includes('VKN_ASR_EVENT'));
 assert.ok(read('content.js').includes('local-asr'));
 assert.ok(read('content.js').includes('开始本地语音听写'));
 assert.ok(read('options.js').includes('qwen2.5:3b'));
 assert.ok(read('stream-client.js').includes("ws://127.0.0.1:8765/asr"));
 assert.ok(!read('offscreen.js').includes('https://api.openai.com'));
});
