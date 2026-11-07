const test = require('node:test');
const assert = require('node:assert/strict');
const Core = require('../extension/core.js');
test('Qwen actual engine metadata survives cleaning; absent scores never become zero',()=>{
  const c=Core.cleanCue({id:'a'.repeat(32)+':1:0',time:0,text:'Hola',source:'local-asr',
    asrEngine:'qwen3-native',asrModel:'Qwen/Qwen3-ASR-1.7B-hf',asrDevice:'cuda:0',
    asrTiming:'aligned_words',asrScoreStatus:'unavailable',confidence:null,languageProbability:null});
  assert.equal(c.asrEngine,'qwen3-native');assert.equal(c.asrScoreStatus,'unavailable');
  assert.equal(c.asrTiming,'aligned_words');assert.equal(c.confidence,undefined);
});
