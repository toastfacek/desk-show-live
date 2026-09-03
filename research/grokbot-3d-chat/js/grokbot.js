/* Zdog PHASEONE grokbot. Mouthless charcoal sphere, amber pills, turning equator. */
(function (global) {
  const CHAR = "#2c2a36";
  const CHAR_BACK = "#221f2a";
  const EQUATOR = "#8a849c";
  const AMBER = "#f0a12a";
  const AMBER_DEEP = "#c47a10";
  const DEG = Math.PI / 180;

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function createGrokbot(canvas, bus) {
    if (typeof Zdog === "undefined") {
      throw new Error("Zdog failed to load");
    }

    const illo = new Zdog.Illustration({
      element: canvas,
      dragRotate: true,
      rotate: { x: -0.18, y: 0.42 },
    });

    const rig = new Zdog.Anchor({ addTo: illo });
    const body = new Zdog.Anchor({ addTo: rig });
    const eyes = new Zdog.Anchor({ addTo: rig, translate: { y: -4, z: 48 } });
    const equator = new Zdog.Anchor({
      addTo: body,
      rotate: { x: Zdog.TAU * 0.07 },
    });

    const diameter = 118;
    new Zdog.Hemisphere({
      addTo: body,
      diameter,
      stroke: false,
      color: CHAR,
      backface: CHAR,
    });
    new Zdog.Hemisphere({
      addTo: body,
      diameter,
      stroke: false,
      color: CHAR_BACK,
      backface: CHAR_BACK,
      rotate: { x: Zdog.TAU / 2 },
    });
    new Zdog.Ellipse({
      addTo: body,
      diameter: 38,
      stroke: false,
      fill: true,
      color: "rgba(255,255,255,0.06)",
      translate: { x: -20, y: -24, z: 42 },
    });

    const radius = diameter / 2 + 0.6;
    const dashes = 32;
    for (let i = 0; i < dashes; i += 1) {
      const a0 = (Zdog.TAU / dashes) * i;
      const a1 = a0 + (Zdog.TAU / dashes) * 0.42;
      new Zdog.Shape({
        addTo: equator,
        path: [
          { x: Math.cos(a0) * radius, y: 0, z: Math.sin(a0) * radius },
          { x: Math.cos(a1) * radius, y: 0, z: Math.sin(a1) * radius },
        ],
        closed: false,
        stroke: 2.4,
        color: EQUATOR,
      });
    }

    function pill(x) {
      return new Zdog.Cylinder({
        addTo: eyes,
        diameter: 15,
        length: 34,
        translate: { x },
        rotate: { x: Zdog.TAU / 4 },
        stroke: false,
        color: AMBER,
        frontFace: AMBER,
        backface: AMBER_DEEP,
      });
    }
    const leftEye = pill(-16);
    const rightEye = pill(16);

    new Zdog.Ellipse({
      addTo: illo,
      diameter: 96,
      stroke: false,
      fill: true,
      color: "rgba(0,0,0,0.28)",
      translate: { y: 78, z: -8 },
      rotate: { x: Zdog.TAU / 4 },
    });

    let dragging = false;
    const canvasEl = canvas;
    canvasEl.addEventListener("pointerdown", () => {
      dragging = true;
    });
    window.addEventListener("pointerup", () => {
      dragging = false;
    });

    let blinkUntil = 0;
    function blink() {
      blinkUntil = performance.now() + 160;
    }
    const blinkTimer = setInterval(() => {
      if (Math.random() < 0.85) blink();
    }, 2800);

    let lastPerf = bus.get();
    bus.subscribe((next) => {
      lastPerf = next;
    });

    let raf = 0;
    function frame(now) {
      const p = lastPerf;
      const emotion = p.emotion;
      const energy = p.energy;
      const squashAmp = p.squash;
      const talking = emotion === "talking" || squashAmp > 0.04;

      equator.rotate.y += dragging ? 0.004 : 0.018;

      let tx = 0;
      let ty = 0;
      let sx = 1;
      let sy = 1;
      let sz = 1;
      let rz = 0;
      let ry = emotion === "listening" ? 0.16 : 0.02;

      if (emotion === "idle" || emotion === "listening") {
        const t = (now / (emotion === "listening" ? 4200 : 3400)) * Zdog.TAU;
        const wave = Math.sin(t);
        ty = wave * -5;
        sx = 1 + wave * 0.015;
        sy = 1 - wave * 0.015;
        sz = sx;
      }

      if (emotion === "thinking") {
        const t = (now / 1800) * Zdog.TAU;
        const wave = Math.sin(t);
        ty = wave * -8;
        rz = -3 * DEG + wave * 7 * DEG;
      }

      if (emotion === "laugh") {
        const t = (now / 280) * Zdog.TAU;
        const wave = Math.sin(t);
        rz = wave * 9 * DEG;
        sx = 1.02 - wave * 0.04;
        sy = 0.96 + wave * 0.09;
        sz = sx;
      }

      if (talking && emotion !== "laugh") {
        const depth = 0.35 + energy * 0.65;
        const drive = squashAmp > 0 ? squashAmp : 0.55 + 0.45 * energy;
        const t = (now / 160) * Zdog.TAU;
        const cycle = (t / Zdog.TAU) % 1;
        let talkSx = 1;
        let talkSy = 1;
        let talkTy = 0;
        if (cycle < 0.35) {
          const u = cycle / 0.35;
          talkTy = lerp(0, 5, u);
          talkSx = lerp(1, 1.055, u);
          talkSy = lerp(1, 0.9, u);
        } else if (cycle < 0.7) {
          const u = (cycle - 0.35) / 0.35;
          talkTy = lerp(5, -4, u);
          talkSx = lerp(1.055, 0.97, u);
          talkSy = lerp(0.9, 1.07, u);
        } else {
          const u = (cycle - 0.7) / 0.3;
          talkTy = lerp(-4, 0, u);
          talkSx = lerp(0.97, 1, u);
          talkSy = lerp(1.07, 1, u);
        }
        sx = lerp(1, talkSx, depth * drive);
        sy = lerp(1, talkSy, depth * drive);
        sz = sx;
        ty = talkTy * drive;
      }

      rig.translate.y = ty;
      rig.rotate.z = rz;
      if (!dragging) rig.rotate.y = lerp(rig.rotate.y || 0, ry, 0.08);
      rig.scale.x = sx;
      rig.scale.y = sy;
      rig.scale.z = sz;

      const blinking = now < blinkUntil;
      let eyeSy = 1;
      let leftY = 0;
      let rightY = 0;
      let leftLen = 34;
      let rightLen = 34;
      let eyeDia = 15;

      if (talking) {
        const t = (now / 160) * Zdog.TAU;
        const cycle = (t / Zdog.TAU) % 1;
        if (cycle < 0.4) eyeSy = lerp(1, 0.78, cycle / 0.4);
        else if (cycle < 0.75) eyeSy = lerp(0.78, 1.08, (cycle - 0.4) / 0.35);
        else eyeSy = lerp(1.08, 1, (cycle - 0.75) / 0.25);
      }

      if (emotion === "happy") {
        leftLen = rightLen = 22;
        eyeDia = 18;
        eyeSy = 1.05;
      } else if (emotion === "thinking") {
        leftLen = rightLen = 18;
        eyeSy = 0.72;
      } else if (emotion === "laugh") {
        leftLen = rightLen = 16;
        eyeSy = 0.62;
      } else if (emotion === "skeptical") {
        leftY = -6;
        rightY = 4;
        rightLen = 26;
        eyeSy = 0.92;
      }

      if (blinking) eyeSy = 0.08;

      eyes.scale.y = eyeSy;
      leftEye.translate.x = -16;
      rightEye.translate.x = 16;
      leftEye.translate.y = leftY;
      rightEye.translate.y = rightY;
      leftEye.length = leftLen;
      rightEye.length = rightLen;
      leftEye.diameter = eyeDia;
      rightEye.diameter = eyeDia;

      const w = canvasEl.clientWidth || 640;
      const h = canvasEl.clientHeight || 520;
      if (canvasEl.width !== w) canvasEl.width = w;
      if (canvasEl.height !== h) canvasEl.height = h;
      illo.zoom = Math.min(w, h) / 210;
      illo.updateRenderGraph();
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return {
      blink,
      illo,
      destroy() {
        cancelAnimationFrame(raf);
        clearInterval(blinkTimer);
      },
    };
  }

  global.GrokbotFace = { createGrokbot };
})(window);
