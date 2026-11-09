// The output remains silent. Only bounded PCM blocks leave the audio thread.
class RelayCapture extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input?.length) {
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const value = Math.max(-1, Math.min(1, input[i]));
        pcm[i] = value * (value < 0 ? 32768 : 32767);
      }
      this.port.postMessage(pcm, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor('relay-capture', RelayCapture);
