const CARD_POLL_MS = 250;

function officialEmbedPath(tweetId, origin) {
  if (typeof tweetId !== "string" || !/^\d{5,25}$/.test(tweetId)) {
    return "";
  }
  return String(origin || "").replace(/\/$/, "") + "/tweet-embed.html?id=" + tweetId + "&theme=dark";
}

function safeImageUrl(raw, origin) {
  if (typeof raw !== "string" || raw === "") {
    return "";
  }
  if (raw.charAt(0) !== "/") {
    return "";
  }
  if (raw.indexOf("://") !== -1 || raw.indexOf("//") === 0) {
    return "";
  }
  return String(origin || "").replace(/\/$/, "") + raw;
}

function applyProducerCard(card, nodes) {
  if (!card || typeof card !== "object") {
    return;
  }
  if (typeof card.author === "string" && nodes.author) {
    nodes.author.textContent = card.author.charAt(0) === "@" ? card.author : "@" + card.author;
  }
  if (typeof card.text === "string" && nodes.body) {
    nodes.body.textContent = card.text;
  }
  if (typeof card.chyron === "string" && nodes.chyron && card.chyron) {
    nodes.chyron.textContent = card.chyron;
  }
  if (typeof card.speaker === "string" && (card.speaker === "a" || card.speaker === "b")) {
    nodes.speaker = card.speaker;
  }
  if (typeof card.layout === "string" && card.layout) {
    nodes.layout = applyOverlayLayout(card.layout, nodes);
  } else if (typeof card.speaker === "string") {
    applyOverlayLayout(nodes.layout || "split", nodes);
  }
  if (nodes.embed) {
    const embedSrc = officialEmbedPath(
      card.tweet_id,
      nodes.embedOrigin || nodes.cardOrigin
    );
    if (embedSrc) {
      if (nodes.embed.src !== embedSrc) {
        nodes.embed.src = embedSrc;
      }
      nodes.embed.hidden = false;
      if (nodes.well && nodes.well.classList) {
        nodes.well.classList.add("has-embed");
      }
    }
  }
  if (nodes.image) {
    const src = safeImageUrl(card.photo_url || "", nodes.cardOrigin);
    if (src) {
      nodes.image.src = src;
      nodes.image.hidden = false;
      if (nodes.panel) {
        nodes.panel.classList.add("has-image");
      }
    }
  }
  if (Array.isArray(card.ticker) && nodes.ticker) {
    const labels = card.ticker.filter(function (item) {
      return typeof item === "string" && item;
    }).slice(0, 6);
    if (labels.length) {
      const line = labels.join("  ·  ");
      nodes.ticker.textContent = line;
      const copies = nodes.tickerCopies;
      if (copies && typeof copies.forEach === "function") {
        copies.forEach(function (el) {
          if (el && el !== nodes.ticker) {
            el.textContent = line;
          }
        });
      }
    }
  }
}

const OVERLAY_LAYOUTS = {
  split: { showA: true, showB: true },
  wide: { showA: true, showB: true },
  solo_l: { showA: true, showB: false },
  solo_r: { showA: false, showB: true },
  card_full: { showA: false, showB: false },
  hold: { showA: false, showB: false },
};

function normalizeLayout(raw) {
  if (raw === "card") {
    return "card_full";
  }
  if (raw && Object.prototype.hasOwnProperty.call(OVERLAY_LAYOUTS, raw)) {
    return raw;
  }
  return "split";
}

function applyOverlayLayout(layout, nodes) {
  const name = normalizeLayout(layout);
  const spec = OVERLAY_LAYOUTS[name];
  const root = nodes && nodes.root;
  if (root && root.classList) {
    Object.keys(OVERLAY_LAYOUTS).forEach(function (item) {
      root.classList.remove("layout-" + item);
    });
    root.classList.add("layout-" + name);
  }
  if (nodes && nodes.hidA) {
    nodes.hidA.hidden = !spec.showA;
    if (spec.showA) {
      const live = !spec.showB || nodes.speaker === "a";
      nodes.hidA.className = live ? "hid live" : "hid idle";
    }
  }
  if (nodes && nodes.hidB) {
    nodes.hidB.hidden = !spec.showB;
    if (spec.showB) {
      const live = !spec.showA || nodes.speaker === "b";
      nodes.hidB.className = live ? "hid live" : "hid idle";
    }
  }
  return name;
}

function layoutFromSearch(search) {
  return normalizeLayout(new URLSearchParams(search || "").get("layout") || "");
}

const EASTERN_TZ = "America/New_York";

function formatEasternClock(date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: EASTERN_TZ,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date instanceof Date ? date : new Date());
  const value = {};
  parts.forEach(function (part) {
    if (part.type !== "literal") {
      value[part.type] = part.value;
    }
  });
  return [value.hour, value.minute, value.second]
    .map(function (item) {
      return String(item || "00").padStart(2, "0");
    })
    .join(":");
}

function cardOriginFromSearch(search, fallback) {
  const params = new URLSearchParams(search || "");
  const raw = params.get("card_origin");
  if (!raw) {
    return fallback;
  }
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return fallback;
    }
    if (parsed.hostname !== "127.0.0.1" && parsed.hostname !== "localhost") {
      return fallback;
    }
    return parsed.origin;
  } catch (_error) {
    return fallback;
  }
}

function bootProducerOverlay() {
  const origin = cardOriginFromSearch(location.search, location.origin);
  const queryLayout = layoutFromSearch(location.search);
  const speaker = new URLSearchParams(location.search).get("speaker") || "a";
  const nodes = {
    author: document.getElementById("card-author"),
    body: document.getElementById("card-body"),
    chyron: document.getElementById("chyron"),
    image: document.getElementById("card-image"),
    ticker: null,
    panel: document.getElementById("card-panel"),
    well: document.getElementById("card-well"),
    embed: document.getElementById("tweet-embed"),
    hidA: document.getElementById("hid-a"),
    hidB: document.getElementById("hid-b"),
    root: document.documentElement,
    speaker: speaker,
    layout: queryLayout,
    cardOrigin: origin,
    embedOrigin: typeof location !== "undefined" ? location.origin : origin,
  };
  applyOverlayLayout(queryLayout, nodes);
  const clock = document.getElementById("clock");
  function tick() {
    if (!clock) {
      return;
    }
    clock.textContent = formatEasternClock(new Date());
  }
  tick();
  setInterval(tick, 1000);

  async function readPreviewLayout() {
    try {
      const response = await fetch(
        (typeof location !== "undefined" ? location.origin : "") + "/layout.json",
        { cache: "no-store" }
      );
      if (!response.ok) {
        return "";
      }
      const payload = await response.json();
      return typeof payload.layout === "string" ? payload.layout : "";
    } catch (_error) {
      return "";
    }
  }

  async function poll() {
    try {
      const response = await fetch(origin + "/card.json", { cache: "no-store" });
      if (response.ok) {
        applyProducerCard(await response.json(), nodes);
      }
    } catch (_error) {
      /* card origin may be down during preview */
    }
    const previewLayout = await readPreviewLayout();
    if (previewLayout) {
      nodes.layout = applyOverlayLayout(previewLayout, nodes);
    } else if (nodes.layout) {
      applyOverlayLayout(nodes.layout, nodes);
    }
  }

  poll();
  setInterval(poll, CARD_POLL_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    applyProducerCard,
    applyOverlayLayout,
    normalizeLayout,
    layoutFromSearch,
    safeImageUrl,
    cardOriginFromSearch,
    officialEmbedPath,
    formatEasternClock,
    EASTERN_TZ,
    OVERLAY_LAYOUTS,
  };
}

if (typeof document !== "undefined") {
  bootProducerOverlay();
}
