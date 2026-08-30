const DEFAULTS = {
  layout: "split",
  headline: "A MOVE WITHOUT A THESIS",
  kicker: "NOW",
  speaking: "host_a",
  show: "RUNTIME",
  presented_by: "REHEARSE",
  names: {
    host_a: { name: "PHASEONE[lol]", handle: "phaseone" },
    host_b: { name: "deb", handle: "deb" },
  },
  center: {
    kind: "card",
    author: "example",
    text: "the vix just did a thing and nobody knows why",
  },
  tickers: {
    sponsors: ["RUNTIME", "DESK SHOW", "REHEARSE", "NO VENDOR IN THIS PACK"],
    markets: ["VIX 14.2", "NDX 19840", "BTC 64210", "NVDA 118.4"],
  },
};

function qs() {
  const p = new URLSearchParams(location.search);
  const out = {};
  if (p.get("layout")) out.layout = p.get("layout");
  if (p.get("headline")) out.headline = p.get("headline");
  if (p.get("speaking")) out.speaking = p.get("speaking");
  return out;
}

function fillTrack(el, items) {
  const sep = "  ·  ";
  const once = items.join(sep);
  el.textContent = `${once}${sep}${once}${sep}`;
}

let tickerKey = "";

function applyState(raw) {
  const s = { ...DEFAULTS, ...raw, names: { ...DEFAULTS.names, ...(raw.names || {}) } };
  const stage = document.getElementById("stage");
  stage.dataset.layout = s.layout;
  stage.dataset.speaking = s.speaking || "";
  stage.dataset.center = (s.center && s.center.kind) || "none";

  document.getElementById("headline").textContent = s.headline || "";
  document.querySelector(".chyron-kicker span").textContent = s.kicker || "NOW";
  document.querySelector(".wordmark").textContent = s.show || "RUNTIME";
  document.querySelector(".presented b").textContent = s.presented_by || "REHEARSE";

  document.getElementById("name-a").textContent = s.names.host_a.name;
  document.getElementById("handle-a").textContent = s.names.host_a.handle;
  document.getElementById("name-b").textContent = s.names.host_b.name;
  document.getElementById("handle-b").textContent = s.names.host_b.handle;
  document.getElementById("name-wide-a").textContent = s.names.host_a.name;
  document.getElementById("name-wide-b").textContent = s.names.host_b.name;

  const card = s.center || {};
  document.getElementById("card-author").textContent = card.author || "";
  document.getElementById("card-text").textContent = card.text || "";

  const nextKey = JSON.stringify(s.tickers || DEFAULTS.tickers);
  if (nextKey !== tickerKey) {
    tickerKey = nextKey;
    const tickers = s.tickers || DEFAULTS.tickers;
    fillTrack(document.getElementById("sponsors"), tickers.sponsors || DEFAULTS.tickers.sponsors);
    fillTrack(document.getElementById("markets"), tickers.markets || DEFAULTS.tickers.markets);
  }
}

function tickClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  document.getElementById("clock").textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

async function poll() {
  try {
    const res = await fetch("../out/overlay_state.json", { cache: "no-store" });
    if (res.ok) applyState(await res.json());
  } catch (_) {
    /* file:// or first run — keep defaults / query params */
  }
}

applyState({ ...DEFAULTS, ...qs() });
tickClock();
setInterval(tickClock, 1000);
setInterval(poll, 250);
poll();

window.applyState = applyState;
