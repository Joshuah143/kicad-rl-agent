// FizzVolt — 3-minute pitch deck (visual-first)
// Compile:  typst compile fizzvolt.typ fizzvolt.pdf

#let bg=rgb("#0B0E14"); #let panel=rgb("#141A24"); #let rule=rgb("#2A3340")
#let ink=rgb("#E8EDF2"); #let dim=rgb("#9AA7B4")
#let accent=rgb("#B6FF3B"); #let accent2=rgb("#3AD7E6"); #let danger=rgb("#FF6B6B")

#set page(
  paper: "presentation-16-9", fill: bg,
  margin: (x: 1.9cm, top: 1.3cm, bottom: 0.9cm),
  footer: context align(right, text(size: 9pt, fill: dim)[FizzVolt · #counter(page).display()]),
)
#set text(font: ("Inter", "Helvetica Neue", "Arial"), fill: ink, size: 15pt)
#set par(leading: 0.55em)
#set list(marker: text(fill: accent)[▸], spacing: 0.6em, body-indent: 7pt)

#let kicker(t) = text(size: 12pt, weight: 700, fill: accent, tracking: 2.5pt)[#upper(t)]
#let head(kick, title) = {
  kicker(kick); v(4pt)
  text(size: 25pt, weight: 800, fill: white)[#title]
  v(4pt); line(length: 100%, stroke: 1pt + rule); v(10pt)
}
#let shot(path, h) = align(center, box(radius: 7pt, clip: true, stroke: 1.2pt + rule)[#image(path, height: h)])
#let stat(num, lab) = align(center)[
  #text(size: 30pt, weight: 900, fill: accent)[#num] #v(-7pt)
  #text(size: 10.5pt, fill: dim, weight: 600)[#upper(lab)]]
#let chip(t, c: accent) = box(fill: panel, stroke: 1pt + c, radius: 5pt, inset: (x: 7pt, y: 5pt))[
  #text(size: 11pt, fill: white, weight: 600)[#t]]
#let arr = text(fill: accent, size: 13pt, weight: 700)[#sym.arrow.r]
#let card(body) = block(width: 100%, fill: panel, radius: 8pt, inset: 12pt, stroke: 1pt + rule)[#body]
#let punch(b) = align(center, text(size: 17pt, weight: 700, fill: white)[#b])

// 1 — TITLE -------------------------------------------------------------------
#v(1fr)
#align(center)[
  #kicker("HUD Hackathon · RL for Hardware")
  #v(10pt)
  #text(size: 80pt, weight: 900, fill: white)[Fizz#text(fill: accent)[Volt]]
  #v(6pt)
  #text(size: 24pt, fill: ink)[We turned the EDA toolchain into a #text(fill: accent, weight: 700)[reward function.]]
  #v(12pt)
  #text(size: 15pt, fill: dim)[Reinforcement learning for verifiable, manufacturable circuit design.]
]
#v(1.4fr)

// 2 — WHY IT'S HARD -----------------------------------------------------------
#pagebreak()
#head("Why it's hard", [One chip. Ten exact connections. _Every time_.])
#grid(columns: (1.4fr, 1fr), gutter: 18pt,
  card[
    #text(size: 11pt, fill: accent2, weight: 700)[FIG 7-1 · TYPICAL APPLICATION — STEP-DOWN REGULATOR]
    #v(7pt)
    #set text(size: 12.5pt)
    #grid(columns: (auto, 1fr), row-gutter: 6pt, column-gutter: 9pt,
      text(fill: accent, weight: 700)[1.], [#raw("C_IN") ≥ 10 µF within 2 mm of VIN→GND],
      text(fill: accent, weight: 700)[2.], [Bootstrap cap #raw("C_BST") 0.1 µF, SW→BST],
      text(fill: accent, weight: 700)[3.], [Divider sets #raw("V_OUT = 0.8·(1+R1/R2)")],
      text(fill: accent, weight: 700)[4.], [Catch Schottky SW→GND, *cathode to SW*],
      text(fill: accent, weight: 700)[5.], [Inductor on SW; #raw("C_OUT") on VOUT→GND],
      text(fill: accent, weight: 700)[6.], [EN pull-up to VIN; keep FB trace short],
    )
    #v(5pt)
    #text(size: 10.5pt, fill: dim, style: "italic")[…and that's one regulator. Now the sensor, the MCU, the USB-C front end…]
  ],
  [
    #stat("~10", "interdependent parts / IC")
    #v(16pt)
    #stat("1", "wrong part = 1 re-spin")
    #v(16pt)
    #card[#align(center)[#text(size: 14pt, fill: white, weight: 700)[Days–weeks lost.] #v(2pt)
      #text(size: 11.5pt, fill: dim)[Blocked team. Delayed launch.]]]
  ],
)

// 3 — WHY AGENTS FAIL ---------------------------------------------------------
#pagebreak()
#head("Why agents fail today", [LLMs write schematics that look right — and #text(fill: danger)[don't build].])
#grid(columns: (1.35fr, 1fr), gutter: 18pt,
  card[
    #set text(size: 13pt)
    #grid(columns: (auto, 1fr), row-gutter: 9pt, column-gutter: 9pt,
      text(fill: danger, weight: 800)[✗], [#raw("D1.1 / D1.2") — LED pins are actually *A / K*],
      text(fill: danger, weight: 800)[✗], [USB-C #raw("CC2") floating — *won't enumerate*],
      text(fill: danger, weight: 800)[✗], [MCU #raw("VDD") with *0 decoupling caps*],
      text(fill: danger, weight: 800)[✗], [Buck stage — *no inductor, no catch diode*],
      text(fill: danger, weight: 800)[✗], [Reasoned for 12 KB of tokens, *emitted no code*],
    )
    #v(6pt)
    #text(size: 10.5pt, fill: dim)[Real failures logged from a strong base model.]
  ],
  [
    #v(8pt)
    #stat("0 / 5", "raw buck attempts that built")
    #v(20pt)
    #align(center)[#text(size: 15pt, fill: white, weight: 700)[Plausible #text(fill: danger)[≠] buildable.]
      #v(8pt) #text(size: 11.5pt, fill: dim)[No verifiable signal → nothing to learn from.]]
  ],
)

// 4 — SOLUTION ----------------------------------------------------------------
#pagebreak()
#head("The solution", [Make the EDA toolchain the #text(fill: accent)[source of truth].])
#grid(columns: (1fr, 1.25fr), gutter: 18pt, align: horizon,
  [
    #align(center)[
      #chip("Prompt")#h(3pt)#arr#h(3pt)#chip("Circuit DSL", c: accent2)#h(3pt)#arr#h(3pt)#chip("Real KiCad", c: accent2)
      #v(5pt)
      #chip("ERC + validators", c: accent2)#h(3pt)#arr#h(3pt)#chip("Reward 0–1")
    ]
    #v(12pt)
    - *Sandboxed DSL* compiles _deterministically_ to real KiCad.
    - *ERC + validators*: correctness, required subcircuits, cost · area · availability · solderability.
    - Every check → one *0–1 reward*.
    - A reproducible *RL gym — 31 tasks*, LED → switching regulators.
  ],
  [#shot("assets/demo_schematic.png", 8.2cm)
   #v(3pt) #align(center)[#text(size: 10pt, fill: dim)[Graded against real KiCad — ERC 0 errors · reward 12.26 / 12.5.]]],
)

// 5 — RL IMPROVEMENT ----------------------------------------------------------
#pagebreak()
#head("The learning loop", [GRPO turns #text(fill: accent)[verification] into improvement.])
#grid(columns: (1fr, 1fr), gutter: 18pt, align: horizon,
  [
    - Sample many designs/task; *reward only those that pass* — no labels, no SPICE.
    - A *rich* reward: ERC · electrical · *completeness* · cost · size · availability.
    - *Within-group variance is the gradient* — sometimes right, sometimes wrong, so it learns.
    - Trained on *HUD* (GRPO · Qwen3-8B / Tinker), graded by *real KiCad*.
    #v(12pt)
    #grid(columns: (1fr, 1fr), stat("8", "reward dimensions"), stat("98%", "of max on passes"))
  ],
  card[
    #text(size: 11pt, fill: accent2, weight: 700)[REWARD BREAKDOWN — one passing design]
    #v(9pt)
    #let bar(lab, frac, c: accent) = grid(columns: (2.9cm, 1fr), column-gutter: 8pt, align: (right+horizon, left+horizon),
      text(size: 11pt, fill: dim)[#lab],
      box(width: 100%)[#box(width: frac*100%, height: 11pt, fill: c, radius: 2pt)])
    #stack(spacing: 7pt,
      bar("erc", 1.0), bar("electrical", 1.0), bar("completeness", 0.9, c: accent2),
      bar("graph", 0.96), bar("cost", 0.8, c: accent2), bar("availability", 0.97),
      bar("size", 0.62, c: accent2))
    #v(8pt)
    #text(size: 10.5pt, fill: dim, style: "italic")[The tools engineers trust become the teacher.]
  ],
)

// 6 — IMPACT ------------------------------------------------------------------
#pagebreak()
#head("The impact", [From a sentence to a #text(fill: accent)[manufacturable board].])
#grid(columns: (1.25fr, 1fr), gutter: 18pt, align: horizon,
  [#shot("assets/demo_3d.png", 8.4cm)
   #v(3pt) #align(center)[#text(size: 10pt, fill: dim)[Schematic → Trace → 3D → *Send to Fab*, graded end-to-end.]]],
  [
    - Attacks a *massive bottleneck*: repetitive datasheet work → *validated automation*.
    - Trusted tools become *automated feedback* → less review, *fewer re-spins*.
    - Compresses *idea → validation → manufacturable hardware*.
    - Next: *PCB layout · placement · routing*.
    #v(12pt)
    #punch[Don't just look right — #text(fill: accent)[build].]
  ],
)
