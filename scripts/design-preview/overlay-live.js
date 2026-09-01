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
  if (nodes.embed) {
    const embedSrc = officialEmbedPath(card.tweet_id, nodes.cardOrigin);
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
      nodes.ticker.textContent = labels.join("  ·  ");
    }
  }
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
  const nodes = {
    author: document.getElementById("card-author"),
    body: document.getElementById("card-body"),
    chyron: document.getElementById("chyron"),
    image: document.getElementById("card-image"),
    ticker: document.getElementById("ticker"),
    panel: document.getElementById("card-panel"),
    well: document.getElementById("card-well"),
    embed: document.getElementById("tweet-embed"),
    cardOrigin: origin,
  };
  const clock = document.getElementById("clock");
  function pad(n) {
    return String(n).padStart(2, "0");
  }
  function tick() {
    if (!clock) {
      return;
    }
    const d = new Date();
    clock.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }
  tick();
  setInterval(tick, 1000);

  const speaker = new URLSearchParams(location.search).get("speaker") || "a";
  const hidA = document.getElementById("hid-a");
  const hidB = document.getElementById("hid-b");
  if (speaker === "b" && hidA && hidB) {
    hidA.className = "hid idle";
    hidB.className = "hid live";
  }

  async function poll() {
    try {
      const response = await fetch(origin + "/card.json", { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      applyProducerCard(await response.json(), nodes);
    } catch (_error) {
      return;
    }
  }

  poll();
  setInterval(poll, CARD_POLL_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    applyProducerCard,
    safeImageUrl,
    cardOriginFromSearch,
    officialEmbedPath,
  };
}

if (typeof document !== "undefined") {
  bootProducerOverlay();
}
