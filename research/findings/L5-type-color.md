# L5 — Type and colour

## Top picks

### Barlow Condensed + Inter — recommended production stack
- **Source:** https://fonts.google.com/specimen/Barlow+Condensed
- **Steal:** Use a compact grotesque for the loud editorial layer and a screen-optimised sans with tabular figures for changing data.
- **Why it serves Runtime:** This directly serves constraints 3 and 4: the condensed face fits short headlines without shrinking them, while the sturdier data face preserves ticker figures at 480p and after Twitch compression.
- **Sourced fact — Barlow Condensed:** Google's live specimen shows nine roman weights and nine italics from 100–900; the project license text is **SIL Open Font License 1.1**: https://github.com/google/fonts/blob/main/ofl/barlowcondensed/OFL.txt. Copyright is held by The Barlow Project Authors. SIL's own FAQ expressly allows OFL fonts in “video titling” without extra permission and says resulting artwork is not forced under OFL: https://software.sil.org/downloads/r/oflt/OFL-FAQ.txt. **Commercial-stream suitability: yes.** Keep the license/copyright with any font files distributed to collaborators; do not sell the font by itself.
- **Sourced fact — Inter:** Google's specimen presents Inter as a variable family designed for computer screens; its project documentation explicitly lists tabular numbers and a slashed zero: https://fonts.google.com/specimen/Inter. The project license is **SIL Open Font License 1.1**: https://github.com/rsms/inter/blob/v4.0/LICENSE.txt. Copyright is held by The Inter Project Authors. **Commercial-stream suitability: yes**, under the same OFL conditions above.
- **Inference — exact Runtime stack:** `"Barlow Condensed", "Inter", sans-serif` for headlines/name bars, and `"Inter", sans-serif` with OpenType `tnum` for tickers, clocks, prices and percentages. Bundle the exact files with the OBS project plus their OFL texts so rendering does not depend on a machine's local fonts.
- **Inference — 1080p settings:** Chyron/headline: Barlow Condensed 700, 42–48 px, uppercase only for a short kicker and sentence case for the actual headline, `0` to `+0.01em` tracking. Host name: 700, 36–40 px, uppercase, `+0.015em`. Role/handle: Inter 600, 26–30 px, sentence/literal case, `0` tracking. Ticker: Inter 600, 26–30 px, tabular figures, `0` tracking. Clock/LIVE: Inter 700, 28–32 px. Do not use weights below 500 or essential text below 26 px on the 1080 canvas; 26 px becomes roughly 12 px in a 480-line delivery.
- **Inference — hierarchy:** Use weight and plate value before size proliferation: one condensed display size, one name size, one data size. Reserve all caps for labels no longer than roughly 12 characters; mixed/sentence case reads faster for headlines and explanatory copy.

### Archivo — one-family variable alternative
- **Source:** https://fonts.google.com/specimen/Archivo
- **Steal:** Use one variable grotesque's width axis to create headline, body and compact-label roles without introducing unrelated visual voices.
- **Why it serves Runtime:** This serves constraints 3 and 4 by allowing width to be tuned before type size is reduced, while preserving a coherent OBS package.
- **Sourced fact:** Google's specimen describes Archivo as a grotesque designed for high-performance print and online typography, with weight and width axes spanning Thin–Black and ExtraCondensed–Expanded. Its license file is **SIL Open Font License 1.1**: https://github.com/google/fonts/blob/main/ofl/archivo/OFL.txt; copyright is held by The Archivo Project Authors. **Commercial-stream suitability: yes**; SIL's FAQ explicitly permits video titling and commercial design outputs under OFL.
- **Inference:** This is the best single-family fallback: use width 70–80 and weight 700 for headlines, width 95–100 and weight 600 for supporting text, and default width with tabular figures only after confirming the chosen build exposes the required numeral feature in OBS. If that feature cannot be confirmed, retain Inter for the data row.

### IBM Plex Sans Condensed + IBM Plex Mono — technical alternate
- **Source:** https://fonts.google.com/specimen/IBM+Plex+Mono
- **Steal:** Pair a condensed sans editorial voice with a visibly engineered mono voice only where fixed-width figures materially improve scanning.
- **Why it serves Runtime:** This serves constraints 3 and 4: fixed-width values stop columns from jumping as data updates, and the related family keeps the package coherent at small output sizes.
- **Sourced fact:** The official IBM repository says the Plex family includes Sans Condensed and Mono and was designed to work in UI environments: https://github.com/IBM/plex. The entire family is under **SIL Open Font License 1.1**, with Reserved Font Name **“Plex”**: https://github.com/IBM/plex/blob/master/LICENSE.txt. **Commercial-stream suitability: yes.** Unmodified use and video output are permitted; a modified font must not retain the reserved name without permission, and redistributed font files must retain license/copyright information.
- **Inference:** Use IBM Plex Sans Condensed 700 for labels and IBM Plex Mono 600 for clocks/market values, not for sentence-length headlines. Mono consumes too much horizontal space for prose; its benefit is stable columns and unambiguous machine-like texture.

### Fey, Origin and OpenSea — dense-data dark UI references
- **Source:** https://mobbin.com/screens/4c06e82d-ede4-49b3-bd0d-62701780688e
- **Steal:** Put neutral text and hairline data structure on near-black surfaces, then reserve restrained warm/cool colour for state and grouping rather than painting every panel.
- **Why it serves Runtime:** This serves constraints 3 and 4 by creating hierarchy chiefly through luminance and solid plates, which is more robust than low-contrast colour detail at 480p.
- **Inspected references:** [Fey](https://mobbin.com/screens/4c06e82d-ede4-49b3-bd0d-62701780688e) uses off-white primary text, subdued gray metadata, and small teal/magenta market marks on nested near-black cards; [Origin](https://mobbin.com/screens/206ca1ac-9c43-4f86-82e8-98c0f24d1140) uses a black/charcoal shell with blue chart lines and compact green/red values; [OpenSea](https://mobbin.com/screens/02a825d8-2758-4c48-bf05-d0b6058d4b5b) uses a dense token table with neutral numerals and green/red deltas. These are **my visual observations from the retrieved screenshots**, not claims made by Mobbin.
- **Inference — palette A, “signal desk”:** foundation `#101116`; raised plate `#171A20`; primary text `#F2F0E8`; secondary text `#A9ADB7`; warm amber `#F2A541`; cool teal `#2FB7B2`; gain `#4FC58B`; loss `#E05D68`.
- **Inference — palette B, “lit bays”:** foundation `#101116`; warm host plate `#5B351F`; cool host plate `#274C52`; primary text `#F2F0E8`; use amber/teal from palette A only as small keys. This gives the warm/cool split to the side boxes while the centre card and ticker remain neutral.
- **Inference — calculated WCAG contrast:** On `#101116`, `#F2F0E8` is 16.52:1, `#A9ADB7` 8.39:1, `#F2A541` 9.19:1, `#2FB7B2` 7.66:1, `#4FC58B` 8.70:1 and `#E05D68` 5.33:1. Dark `#101116` text on amber is 9.19:1 and on teal 7.66:1. Off-white on the warm and cool plates is 9.32:1 and 8.21:1 respectively. Ratios were calculated from the WCAG relative-luminance formula; they are design calculations, not values stated by the references.

### BBC GEL + W3C — solid-plate accessibility rule
- **Source:** https://www.bbc.com/gel/features/typography
- **Steal:** Establish a small fixed type scale and require every text/background token pair to pass contrast before it can enter a live template.
- **Why it serves Runtime:** This serves constraints 3 and 4 by preventing contrast from changing with the generated hosts and set behind the deterministic OBS layer.
- **Sourced fact:** BBC GEL uses a limited size/style scale, reserves heavier weights mainly for headlines/titles/links, and requires WCAG AA contrast. W3C specifies at least **4.5:1 for normal text** and **3:1 for large text**: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum. W3C also says colour must not be the only means of conveying information: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html.
- **Inference:** Treat all Runtime ticker and secondary copy as “normal text” and target at least **7:1**, not merely 4.5:1, because encoder loss, living-room distance and 480p downscaling add impairment not modelled by WCAG. Put every essential line on an opaque or near-opaque solid plate; do not rely on a drop shadow over moving video. Use `▲ +0.8%` and `▼ −0.8%` (shape/sign plus colour), never green/red alone.

### Bloomberg Television redesign study — disciplined finance density
- **Source:** https://markporter.com/work/bloomberg-television
- **Steal:** Reduce the number of simultaneous feeds, then make the remaining information more playful through scale and placement rather than ornamental effects.
- **Why it serves Runtime:** This serves constraints 3 and 4 by prioritising readable data without sacrificing the live action or spending the limited bitrate on decoration.
- **Sourced fact:** The case study says clutter was the central problem in financial television and describes cleaning up a “J screen” of headlines and figures so it would not compromise live action. It also explicitly pairs rigorous data visualisation with a bolder editorial voice.
- **Inference:** Runtime should show one ticker row, one active headline bar and one centre card, not a finance-channel wall of simultaneous microtext. Let Barlow Condensed supply the editorial character while Inter carries factual data.

### Sports Final package — broadcast hierarchy and template discipline
- **Source:** https://msanchez.co/sports-final
- **Steal:** Build a small family of reusable lower-third templates with locked non-content layers and explicit text-length rules.
- **Why it serves Runtime:** This serves constraints 3 and 4 because controlled templates preserve type sizes, colours and hierarchy under live updates instead of allowing one-off operator choices.
- **Sourced fact:** The designer reports choosing DIN 2014 for a strong, clean all-caps sports-news voice and building generic, identity and analysis lower thirds around flexible templates. This is a case-study claim, not proof that DIN itself performs better after compression.
- **License note:** DIN 2014 is **not an open-font recommendation**. Adobe identifies Paratype's DIN 2014 and says the Adobe Fonts library permits in-house or commercial video/broadcast use: https://fonts.adobe.com/fonts/din-2014. **Commercial-stream suitability: yes only under the applicable Adobe Fonts/Creative Cloud terms**; self-hosting, app embedding and other uses may require separate Paratype licensing. Runtime should use Barlow Condensed instead to avoid a subscription and seat-management dependency.

### MSI 24 esports identity — bold system, muted for delivery
- **Source:** https://studiodumbar.com/work/msi-24
- **Steal:** Define one bold typographic attitude, one dominant dark field and a tightly controlled accent behaviour that repeats across every template.
- **Why it serves Runtime:** This serves constraint 4 by reducing the package to robust repeated primitives, provided the reference's saturated effects are translated into larger, flatter shapes.
- **Sourced fact:** Studio Dumbar describes a multi-vendor package built from bold expressive typography, a black/red primary palette, data-like textures, icons, templates and detailed guidelines. The image-rich [Warzone Total Frenzy Behance case](https://www.behance.net/gallery/204859679/WTF-Warzone-Total-Frenzy) similarly describes a modular framework that can vary palettes and themes while preserving its identity.
- **Inference:** Take the governance, not the red-heavy execution: use Runtime's amber and teal as broad blocks or thick rules, and keep animated texture out of ticker text. A repeated 6–8 px 1080p keyline will survive downscale better than intricate “data” patterns.

## Avoid

1. **Thin, light or hairline type and one-pixel rules.** They are tempting in dense finance UI, but constraint 4 makes them fragile after downscale and compression. Use 500–700 weights and no essential stroke below 2 px at 1080p; prefer 3–4 px for rules that must remain visible at 480p.
2. **Pure or highly saturated red/blue text on dark or gray video.** The SMPTE paper “Toward Better Chroma Subsampling” finds chroma errors are worst at full saturation and shows red text becoming noticeably blurry under subsampling: https://doi.org/10.5594/j15100. Keep loss red muted, use it on large chips or thick arrows, and render the actual numeral in high-luminance neutral text.
3. **Text directly over the generated frame, translucent glass, fine gradients or dither.** Their local contrast changes every five-second take, and gradients/dither spend bitrate without producing stable hierarchy. Use opaque `#101116`/`#171A20` plates; a shadow may supplement a plate but never replace it.
4. **Over-condensing ticker prose or setting long headlines in all caps.** Condensed display type saves width but closes counters and slows sentence scanning at small sizes. Keep Barlow Condensed for short display lines; keep ticker prose and metadata in Inter mixed case.
5. **Cloning a proprietary finance/sports package or making DIN 2014 the default dependency.** The former violates the no-IP-cloning constraint; the latter is legal for commercial broadcast through Adobe Fonts but introduces subscription/account constraints. Use the sourced OFL stack and translate references into general hierarchy, density and palette techniques.

## What I could not answer

- I did not find a primary Twitch document that states the exact chroma-subsampling path or quantisation applied to every live transcode. The compression warnings therefore combine the brief's known Twitch constraint with SMPTE's tested subsampling behaviour; the exact failure threshold for Runtime remains unknown.
- No source can guarantee a minimum safe font size for this specific OBS → Twitch bitrate → 480p path. The 26 px minimum and 2–4 px stroke guidance are my conservative inference and must be validated with a private encode of the actual scene.
- Mobbin does not identify the exact fonts or publish design-token RGB values for the three supplied screenshots. I inspected the retrieved full screenshots, but the palette descriptions are visual inference rather than authoritative brand specifications.
- Public X searches did not return a retrievable, relevant designer post. I have not substituted an unverified or guessed X URL.
- Behance text and project pages were retrievable, but some embedded image/media payloads timed out in the text fetcher. I used only the authors' written claims from those pages and did not infer uninspected motion details.
- Whether OBS/browser-source rendering exposes every variable axis and OpenType feature consistently on the target machine remains untested. Pin static font instances where possible and verify `tnum` in the actual renderer.
