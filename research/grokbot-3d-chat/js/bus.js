/* Performance bus. Brain writes text + emotion. Voice writes squash. Renderer reads. */
(function (global) {
  const EMOTIONS = Object.freeze([
    "idle",
    "talking",
    "thinking",
    "listening",
    "laugh",
    "happy",
    "skeptical",
  ]);

  function clamp01(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  function emotionOf(value) {
    return EMOTIONS.includes(value) ? value : "idle";
  }

  function createBus(initial) {
    const listeners = new Set();
    const state = {
      emotion: "idle",
      energy: 0.25,
      thinking: false,
      squash: 0,
      text: "",
      ...initial,
    };

    function snapshot() {
      return {
        emotion: state.emotion,
        energy: state.energy,
        thinking: state.thinking,
        squash: state.squash,
        text: state.text,
      };
    }

    function emit() {
      const next = snapshot();
      listeners.forEach((fn) => fn(next));
    }

    return {
      EMOTIONS,
      get: snapshot,
      subscribe(fn) {
        listeners.add(fn);
        fn(snapshot());
        return () => listeners.delete(fn);
      },
      set(partial) {
        if (!partial || typeof partial !== "object") return snapshot();
        if ("emotion" in partial) state.emotion = emotionOf(partial.emotion);
        if ("energy" in partial) state.energy = clamp01(partial.energy);
        if ("thinking" in partial) state.thinking = Boolean(partial.thinking);
        if ("squash" in partial) state.squash = clamp01(partial.squash);
        if ("text" in partial) state.text = String(partial.text || "");
        emit();
        return snapshot();
      },
      applyPerformance(perf, text) {
        const performance = perf && typeof perf === "object" ? perf : {};
        return this.set({
          emotion: emotionOf(performance.emotion),
          energy: clamp01(performance.energy == null ? 0.55 : performance.energy),
          thinking: Boolean(performance.thinking),
          text: text == null ? state.text : String(text),
        });
      },
    };
  }

  global.GrokbotBus = { EMOTIONS, clamp01, emotionOf, createBus };
})(window);
