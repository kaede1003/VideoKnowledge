/* 16 kHz mono PCM16 from the captured tab; no network here. */
class VknSpeechProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.previous = 0;
    this.inputIndex = 0;
    this.nextSampleIndex = 0;
    this.step = sampleRate / 16000;
    this.samples = new Int16Array(3200); // 200 ms to the offscreen page
    this.offset = 0;
    this.gated = false;
    this.port.onmessage = e => {
      const m=e.data||{};
      if(m.type==='gate'){
        if(this.offset){const out=this.samples.slice(0,this.offset);this.port.postMessage(out,[out.buffer]);this.samples=new Int16Array(3200);this.offset=0;}
        this.gated=!!m.paused;
        this.port.postMessage({type:'gated',id:m.id});
      }
    };
  }
  process(inputs) {
    if(this.gated)return true;
    const channels = inputs[0];
    if (!channels || !channels.length || !channels[0]) return true;
    const n = channels[0].length;
    for (let i = 0; i < n; ++i) {
      let current = 0;
      for (let c = 0; c < channels.length; ++c) current += channels[c][i] || 0;
      current /= channels.length;
      const index = this.inputIndex++;
      while (this.nextSampleIndex <= index) {
        const frac = Math.max(0, Math.min(1, this.nextSampleIndex - (index - 1)));
        const sample = this.previous + (current - this.previous) * frac;
        this.samples[this.offset++] = Math.round(Math.max(-1, Math.min(1, sample)) * 32767);
        if (this.offset === this.samples.length) {
          const ready = this.samples;
          this.port.postMessage(ready, [ready.buffer]);
          this.samples = new Int16Array(3200);
          this.offset = 0;
        }
        this.nextSampleIndex += this.step;
      }
      this.previous = current;
    }
    return true;
  }
}
registerProcessor('vkn-speech-processor', VknSpeechProcessor);
