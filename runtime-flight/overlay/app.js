const STALE_MS = 1200;
const POLL_MS = 250;

function shouldShowHold(state) {
  if (state.unreachable) {
    return true;
  }
  if (state.healthy === false) {
    return true;
  }
  if (typeof state.age_ms === "number" && state.age_ms > STALE_MS) {
    return true;
  }
  if (typeof state.receiptAgeMs === "number" && state.receiptAgeMs > STALE_MS) {
    return true;
  }
  return false;
}

function applyCard(card, nodes) {
  nodes.author.textContent = card.author || "";
  nodes.tweet.textContent = card.text || "";
  nodes.timestamp.textContent = card.timestamp || "";
}

function applyHold(showHold) {
  document.body.classList.toggle("hold", showHold);
}

function bootOverlay() {
  const nodes = {
    author: document.getElementById("author"),
    tweet: document.getElementById("tweet"),
    timestamp: document.getElementById("timestamp"),
  };
  let lastSuccessNow = null;
  let lastHeartbeat = null;
  let unreachable = true;

  function snapshot(now) {
    return {
      unreachable,
      healthy: lastHeartbeat ? lastHeartbeat.healthy : false,
      age_ms: lastHeartbeat ? lastHeartbeat.age_ms : STALE_MS + 1,
      receiptAgeMs: lastSuccessNow == null ? STALE_MS + 1 : now - lastSuccessNow,
    };
  }

  function render() {
    applyHold(shouldShowHold(snapshot(performance.now())));
  }

  async function poll() {
    try {
      const heartbeatResponse = await fetch("/heartbeat.json", { cache: "no-store" });
      if (!heartbeatResponse.ok) {
        throw new Error("heartbeat");
      }
      const heartbeat = await heartbeatResponse.json();
      lastSuccessNow = performance.now();
      unreachable = false;
      lastHeartbeat = heartbeat;
      const cardResponse = await fetch("/card.json", { cache: "no-store" });
      if (cardResponse.ok) {
        applyCard(await cardResponse.json(), nodes);
      }
    } catch (_error) {
      unreachable = true;
    }
    render();
  }

  function frame() {
    render();
    requestAnimationFrame(frame);
  }

  poll();
  setInterval(poll, POLL_MS);
  requestAnimationFrame(frame);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { STALE_MS, shouldShowHold, applyCard };
}

if (typeof document !== "undefined") {
  bootOverlay();
}
