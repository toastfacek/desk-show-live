/* Wire chat well, bus, face, voice. One host. Composer never sticks shut. */
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
  let liveBrain = false;
  let recognition = null;
  let watchdog = 0;
  let turn = 0;

  const canvas = document.getElementById("stage");
  const logEl = document.getElementById("log");
  const form = document.getElementById("composer");
  const input = document.getElementById("comment");
  const sendBtn = document.getElementById("send");
  const talkBtn = document.getElementById("talk");
  const stateEl = document.getElementById("face-state");
  const lineEl = document.getElementById("spoken");
  const hudEl = document.getElementById("hud");
  const muteBtn = document.getElementById("mute");
  const brainEl = document.getElementById("brain-source");
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;

  try {
    GrokbotFace.createGrokbot(canvas, bus);
  } catch (err) {
    lineEl.textContent = "Face failed to load. Chat still works — type below.";
    console.error(err);
  }

  if (!Rec && talkBtn) {
    talkBtn.hidden = true;
  }

  function setListeningUi(on) {
    if (!talkBtn) return;
    talkBtn.setAttribute("aria-pressed", String(on));
    talkBtn.textContent = on ? "Listening…" : "Talk";
  }

  function stopListen() {
    if (recognition) {
      try {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.stop();
      } catch (_err) {
        /* ignore */
      }
      recognition = null;
    }
    setListeningUi(false);
  }

  function clearWatchdog() {
    if (watchdog) {
      clearTimeout(watchdog);
      watchdog = 0;
    }
  }

  function setBusy(next) {
    busy = next;
    if (sendBtn) sendBtn.disabled = next;
    if (input) input.disabled = false;
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

  function finishTurn(mine) {
    if (mine !== turn) return;
    clearWatchdog();
    bus.set({
      emotion: "listening",
      thinking: false,
      energy: 0.25,
      squash: 0,
    });
    setBusy(false);
    input.focus();
  }

  async function handleComment(text) {
    const comment = String(text || "").trim();
    if (!comment) return;
    stopListen();
    voice.stop();
    turn += 1;
    const mine = turn;
    setBusy(true);
    clearWatchdog();
    watchdog = setTimeout(() => {
      if (mine !== turn) return;
      lineEl.textContent = "I lost that line. Type again.";
      finishTurn(mine);
    }, 14000);
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
    let packet;
    try {
      const [next] = await Promise.all([
        GrokbotBrain.thinkThenReply(comment, history, { live: liveBrain }),
        thinkHold,
      ]);
      packet = next;
    } catch (_err) {
      packet = GrokbotBrain.stubReply(comment, history);
    }
    if (mine !== turn) return;
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
    voice.speak(packet.text, () => finishTurn(mine));
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = input.value;
    input.value = "";
    handleComment(value);
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      handleComment(button.getAttribute("data-sample"));
    });
  });

  function startListen() {
    if (!Rec) {
      lineEl.textContent = "This browser can't hear you. Type in the well.";
      input.focus();
      return;
    }
    if (recognition) {
      stopListen();
      return;
    }
    const rec = new Rec();
    recognition = rec;
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (event) => {
      const last = event.results[event.results.length - 1];
      const heard = String(last[0].transcript || "").trim();
      input.value = heard;
      if (last.isFinal && heard) {
        stopListen();
        input.value = "";
        handleComment(heard);
      }
    };
    rec.onerror = (event) => {
      stopListen();
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        lineEl.textContent = "Mic blocked. Type in the well.";
      } else if (event.error !== "aborted") {
        lineEl.textContent = "I didn't catch that. Type it.";
      }
      input.focus();
    };
    rec.onend = () => {
      if (recognition === rec) stopListen();
    };
    setListeningUi(true);
    lineEl.textContent = "listening…";
    bus.set({ emotion: "listening", thinking: false, energy: 0.3, squash: 0 });
    try {
      rec.start();
    } catch (_err) {
      stopListen();
      lineEl.textContent = "Mic didn't start. Type in the well.";
      input.focus();
    }
  }

  if (talkBtn) {
    talkBtn.addEventListener("click", () => {
      startListen();
    });
  }

  fetch("/api/health")
    .then((r) => (r.ok ? r.json() : null))
    .then((info) => {
      if (!info) return;
      liveBrain = info.brain === "live";
      if (brainEl) brainEl.textContent = liveBrain ? "live text model" : "stub brain";
    })
    .catch(() => {});

  input.focus();
})();
