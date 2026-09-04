/* Speech-rate clock. Audio (or a timer) drives squash. Not the LLM. */
(function (global) {
  function estimateMs(text) {
    const chars = String(text || "").length;
    return Math.max(1100, Math.min(9000, 420 + chars * 58));
  }

  function createVoice(bus, options) {
    const opts = options || {};
    let muted = Boolean(opts.muted);
    let tick = 0;
    let fallback = 0;
    let speaking = false;
    let generation = 0;

    function clearTimers() {
      if (tick) {
        clearInterval(tick);
        tick = 0;
      }
      if (fallback) {
        clearTimeout(fallback);
        fallback = 0;
      }
    }

    function stopSpeech() {
      if (global.speechSynthesis) {
        try {
          global.speechSynthesis.cancel();
        } catch (_err) {
          /* ignore */
        }
      }
    }

    function finish(mine, onEnd) {
      if (mine !== generation) return;
      speaking = false;
      clearTimers();
      bus.set({ squash: 0 });
      if (onEnd) onEnd();
    }

    function runClock(mine, text, onEnd) {
      const started = performance.now();
      const duration = estimateMs(text);
      speaking = true;
      tick = setInterval(() => {
        if (mine !== generation) return;
        const elapsed = performance.now() - started;
        if (elapsed >= duration) {
          finish(mine, onEnd);
          return;
        }
        const energy = bus.get().energy;
        const wave = Math.abs(Math.sin((elapsed / 1000) * 6 * Math.PI * 2));
        bus.set({ squash: 0.35 + 0.65 * wave * (0.4 + 0.6 * energy) });
      }, 32);
      fallback = setTimeout(() => finish(mine, onEnd), duration + 40);
    }

    function speak(text, onEnd) {
      generation += 1;
      const mine = generation;
      stopSpeech();
      clearTimers();
      const line = String(text || "").trim();
      if (!line) {
        finish(mine, onEnd);
        return;
      }
      const synth = global.speechSynthesis;
      if (!muted && synth) {
        const utter = new SpeechSynthesisUtterance(line);
        utter.rate = 1.04;
        utter.pitch = 0.82;
        utter.volume = 0.9;
        const voices = synth.getVoices() || [];
        const pick = voices.find((v) => /en[-_]?US/i.test(v.lang) && /Google|Samantha|Daniel|Natural/i.test(v.name))
          || voices.find((v) => /^en/i.test(v.lang));
        if (pick) utter.voice = pick;
        let started = false;
        utter.onstart = () => {
          if (mine !== generation) return;
          started = true;
          runClock(mine, line, onEnd);
        };
        utter.onend = () => {
          if (speaking) finish(mine, onEnd);
        };
        utter.onerror = () => {
          if (!started && mine === generation) runClock(mine, line, onEnd);
        };
        try {
          synth.speak(utter);
          fallback = setTimeout(() => {
            if (!started && mine === generation) runClock(mine, line, onEnd);
          }, 280);
          return;
        } catch (_err) {
          runClock(mine, line, onEnd);
          return;
        }
      }
      runClock(mine, line, onEnd);
    }

    return {
      speak,
      stop() {
        generation += 1;
        stopSpeech();
        clearTimers();
        speaking = false;
        bus.set({ squash: 0 });
      },
      setMuted(next) {
        muted = Boolean(next);
        if (muted) stopSpeech();
      },
      get muted() {
        return muted;
      },
    };
  }

  global.GrokbotVoice = { createVoice, estimateMs };
})(window);
