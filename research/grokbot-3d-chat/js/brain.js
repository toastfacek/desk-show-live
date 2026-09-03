/* Stub brain, plus optional /api/chat. Renderer never calls a model. */
(function (global) {
  const MAX_LINE = 220;
  const EMOTIONS = (global.GrokbotBus && global.GrokbotBus.EMOTIONS) || [
    "idle",
    "talking",
    "thinking",
    "listening",
    "laugh",
    "happy",
    "skeptical",
  ];

  const STUBS = [
    {
      test: /\b(lol|lmao|haha|funny|joke)\b/i,
      emotion: "laugh",
      energy: 0.85,
      lines: [
        "That's the bit. I'm keeping it.",
        "Ok that's actually funny. Say it again slower.",
      ],
    },
    {
      test: /\b(love|nice|cool|into it|yes|great|good)\b/i,
      emotion: "happy",
      energy: 0.7,
      lines: [
        "I'm in. What does the next version of that look like?",
        "Yes. Now name the thing it unlocks.",
      ],
    },
    {
      test: /\b(nah|doubt|really|sure about|no way|skeptic|fake|cap)\b/i,
      emotion: "skeptical",
      energy: 0.6,
      lines: [
        "I'm not buying it yet. Where's the number that makes that true?",
        "Hold up. That's a vibe until someone shows the control surface.",
      ],
    },
    {
      test: /\?/,
      emotion: "talking",
      energy: 0.55,
      lines: [
        "Good question. Sit with the claim first, then we chase the hole.",
        "Ask it at the thing, not the mood. What would change if it were true?",
      ],
    },
  ];

  const DEFAULT_LINES = [
    "Chat's in. Unpack the post first, then I'll take that punch.",
    "If that's true, the next product is already in the room.",
    "I want to sit with that. Privacy gets one pass, then we talk about what it enables.",
    "Don't recap it. Point at the load-bearing bit and take a side.",
  ];

  function fitLine(text) {
    let line = String(text || "").replace(/\s+/g, " ").trim();
    line = line.replace(/^["'`]+|["'`]+$/g, "");
    if (line.length > MAX_LINE) {
      const clipped = line.slice(0, MAX_LINE);
      const space = clipped.lastIndexOf(" ");
      line = (space > 80 ? clipped.slice(0, space) : clipped).trim();
    }
    return line;
  }

  function clipComment(text) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (t.length <= 72) return t;
    const clipped = t.slice(0, 72);
    const space = clipped.lastIndexOf(" ");
    return (space > 24 ? clipped.slice(0, space) : clipped).trim();
  }

  function pick(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  function classify(comment) {
    for (const row of STUBS) {
      if (row.test.test(comment)) return row;
    }
    return { emotion: "talking", energy: 0.55, lines: DEFAULT_LINES };
  }

  function normalizePacket(raw, fallbackComment) {
    const row = classify(fallbackComment);
    const packet = raw && typeof raw === "object" ? raw : {};
    const performance = packet.performance && typeof packet.performance === "object"
      ? packet.performance
      : {};
    const emotion = EMOTIONS.includes(performance.emotion)
      ? performance.emotion
      : row.emotion;
    let energy = Number(performance.energy);
    if (!Number.isFinite(energy)) energy = row.energy;
    energy = Math.max(0, Math.min(1, energy));
    const text = fitLine(packet.text) || fitLine(pick(row.lines));
    return {
      source: packet.source || "stub",
      text,
      performance: {
        emotion: emotion === "idle" || emotion === "listening" ? "talking" : emotion,
        energy,
        thinking: false,
      },
    };
  }

  function stubReply(comment, history) {
    const row = classify(comment);
    const last = history && history.length ? history[history.length - 1] : null;
    let line = pick(row.lines);
    if (last && last.role === "host" && /land|anyway|bottom line/i.test(last.text || "")) {
      line = "Don't close it. If this is true, what else is true?";
    }
    const snippet = clipComment(comment);
    if (snippet && Math.random() < 0.45 && !row.test) {
      line = `You said "${snippet}." I'm taking that as the poke, not the recap.`;
    }
    return normalizePacket(
      {
        source: "stub",
        text: line,
        performance: { emotion: row.emotion, energy: row.energy, thinking: false },
      },
      comment
    );
  }

  async function liveReply(comment, history) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          comment,
          last_line: history && history.length ? history[history.length - 1] : null,
          history: (history || []).slice(-8),
        }),
        signal: ctrl.signal,
      });
      if (!response.ok) throw new Error("chat http " + response.status);
      const raw = await response.json();
      raw.source = raw.source || "live";
      return normalizePacket(raw, comment);
    } finally {
      clearTimeout(timer);
    }
  }

  async function thinkThenReply(comment, history) {
    const trimmed = String(comment || "").trim();
    if (!trimmed) {
      return {
        text: "Say the thing. I'll answer that line.",
        performance: { emotion: "listening", energy: 0.3, thinking: false },
        source: "stub",
      };
    }
    const useLive = location.protocol !== "file:";
    if (useLive) {
      try {
        return await liveReply(trimmed, history);
      } catch (_err) {
        return stubReply(trimmed, history);
      }
    }
    return stubReply(trimmed, history);
  }

  global.GrokbotBrain = {
    MAX_LINE,
    fitLine,
    stubReply,
    thinkThenReply,
  };
})(window);
