/* Wire chat well, bus, face, voice. One host. */
(function () {
  const bus = GrokbotBus.createBus({
    emotion: "listening",
    energy: 0.25,
    thinking: false,
    squash: 0,
  });
  const voice = GrokbotVoice.createVoice(bus, { muted: false });
  const history = [];
  let busy = false;

  const canvas = document.getElementById("stage");
  const logEl = document.getElementById("log");
  const form = document.getElementById("composer");
  const input = document.getElementById("comment");
  const sendBtn = document.getElementById("send");
  const stateEl = document.getElementById("face-state");
  const lineEl = document.getElementById("spoken");
  const hudEl = document.getElementById("hud");
  const muteBtn = document.getElementById("mute");
  const brainEl = document.getElementById("brain-source");

  GrokbotFace.createGrokbot(canvas, bus);

  function setBusy(next) {
    busy = next;
    sendBtn.disabled = next;
    input.disabled = next;
  }

  function appendMessage(role, text) {
    const li = document.createElement("li");
    li.className = "msg msg-" + role;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "chat" ? "CHAT" : "HOST";
    const body = document.createElement("p");
    body.textContent = text;
    li.append(who, body);
    logEl.appendChild(li);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function renderHud(state) {
    stateEl.textContent = state.emotion;
    stateEl.dataset.emotion = state.emotion;
    hudEl.textContent = JSON.stringify(
      {
        emotion: state.emotion,
        energy: Number(state.energy.toFixed(2)),
        thinking: state.thinking,
        squash: Number(state.squash.toFixed(2)),
      },
      null,
      0
    );
    if (state.text) lineEl.textContent = state.text;
  }

  bus.subscribe(renderHud);

  document.querySelectorAll("[data-mood]").forEach((button) => {
    button.addEventListener("click", () => {
      if (busy) return;
      const emotion = button.getAttribute("data-mood");
      bus.set({
        emotion,
        thinking: emotion === "thinking",
        energy: emotion === "laugh" ? 0.9 : 0.45,
        squash: emotion === "talking" ? 0.7 : 0,
        text: emotion === "talking" ? "Mood board. Not a line." : bus.get().text,
      });
    });
  });

  muteBtn.addEventListener("click", () => {
    const next = !voice.muted;
    voice.setMuted(next);
    muteBtn.setAttribute("aria-pressed", String(next));
    muteBtn.textContent = next ? "Sound off" : "Sound on";
  });

  async function handleComment(text) {
    const comment = String(text || "").trim();
    if (!comment || busy) return;
    voice.stop();
    setBusy(true);
    appendMessage("chat", comment);
    history.push({ role: "chat", text: comment });
    bus.set({
      emotion: "thinking",
      thinking: true,
      energy: 0.35,
      squash: 0,
      text: "",
    });
    lineEl.textContent = "thinking…";
    const thinkHold = new Promise((resolve) => setTimeout(resolve, 520 + Math.random() * 420));
    const [packet] = await Promise.all([
      GrokbotBrain.thinkThenReply(comment, history),
      thinkHold,
    ]);
    if (brainEl) brainEl.textContent = packet.source === "live" ? "live text model" : "stub brain";
    const spokenEmotion = packet.performance.emotion === "thinking"
      ? "talking"
      : packet.performance.emotion;
    bus.applyPerformance(
      { ...packet.performance, emotion: spokenEmotion, thinking: false },
      packet.text
    );
    if (spokenEmotion !== "talking" && spokenEmotion !== "laugh") {
      bus.set({ squash: 0.55 });
    }
    appendMessage("host", packet.text);
    history.push({ role: "host", text: packet.text });
    voice.speak(packet.text, () => {
      bus.set({
        emotion: "listening",
        thinking: false,
        energy: 0.25,
        squash: 0,
      });
      setBusy(false);
      input.focus();
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = input.value;
    input.value = "";
    handleComment(value);
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      if (busy) return;
      handleComment(button.getAttribute("data-sample"));
    });
  });

  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : null))
    .then((info) => {
      if (info && brainEl) {
        brainEl.textContent = info.brain === "live" ? "live text model" : "stub brain";
      }
    })
    .catch(() => {});

  input.focus();
})();
