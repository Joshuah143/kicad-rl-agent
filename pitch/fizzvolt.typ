// FizzVolt — 3-minute pitch deck · modern light theme (minimal text)
// Compile:  typst compile fizzvolt.typ fizzvolt.pdf

// ---- design tokens ---------------------------------------------------------
#let paper  = rgb("#F7F8FA")
#let card   = rgb("#FFFFFF")
#let border = rgb("#E6E8EE")
#let ink    = rgb("#0C1124")
#let body   = rgb("#3A4256")
#let sub    = rgb("#6B7488")
#let faint  = rgb("#A2AAB9")
#let brand  = rgb("#4F46E5")
#let brand2 = rgb("#9333EA")
#let cyan   = rgb("#0891B2")
#let good   = rgb("#16A34A")
#let bad    = rgb("#E5484D")
#let mono   = ("DejaVu Sans Mono",)
#let grad   = gradient.linear(brand, brand2, angle: 20deg)

#set page(
  paper: "presentation-16-9", fill: paper,
  margin: (x: 2.0cm, top: 1.2cm, bottom: 0.85cm),
  footer: context align(right, text(font: mono, size: 8.5pt, fill: faint)[
    FIZZVOLT · #counter(page).display("01")]),
)
#set text(font: ("Inter", "Helvetica Neue", "Arial"), fill: body, size: 15pt)
#set par(leading: 0.62em)

// ---- components ------------------------------------------------------------
#let kicker(n, t) = text(font: mono, size: 10.5pt, fill: brand, weight: 700)[
  #n#h(6pt)#text(fill: faint)[/]#h(6pt)#text(fill: sub, weight: 600)[#upper(t)]]

#let head(n, t, title) = {
  kicker(n, t); v(5pt)
  text(size: 26pt, weight: 800, fill: ink, tracking: -0.5pt)[#title]
  v(6pt); line(length: 100%, stroke: 1pt + border); v(12pt)
}

#let panel(b) = block(width: 100%, fill: card, radius: 13pt, inset: 12pt, stroke: 1pt + border)[#b]
#let shot(path, h) = align(center, box(radius: 12pt, clip: true, stroke: 1pt + border)[#image(path, height: h)])
#let pill(t, c) = box(fill: c.lighten(86%), radius: 20pt, inset: (x: 9pt, y: 4pt))[
  #text(size: 10.5pt, fill: c.darken(8%), weight: 700)[#t]]
#let tag(t) = box(fill: card, stroke: 1pt + border, radius: 9pt, inset: (x: 11pt, y: 8pt))[
  #text(size: 13pt, fill: ink, weight: 600)[#t]]
#let tags(..items) = block(spacing: 9pt)[#items.pos().map(t => tag(t)).join(h(7pt))]
#let stat(num, lab) = align(center)[
  #text(size: 36pt, weight: 800, fill: ink, tracking: -0.5pt)[#num] #v(-7pt)
  #text(font: mono, size: 9.5pt, fill: sub, weight: 600)[#upper(lab)]]
#let chip(t, c: brand) = box(fill: c.lighten(90%), stroke: 1pt + c.lighten(55%), radius: 8pt, inset: (x: 9pt, y: 7pt))[
  #text(size: 11.5pt, fill: c.darken(10%), weight: 700)[#t]]
#let arr = text(fill: faint, size: 13pt, weight: 700)[#sym.arrow.r]

// ============================================================================
// 1 — TITLE
// ============================================================================
#v(1fr)
#align(center)[
  #box(inset: (x: 11pt, y: 6pt), radius: 20pt, fill: brand.lighten(88%))[
    #text(font: mono, size: 10.5pt, fill: brand, weight: 700)[HUD HACKATHON · RL FOR HARDWARE]]
  #v(16pt)
  #text(size: 74pt, weight: 900, tracking: -2pt)[#text(fill: ink)[Fizz]#text(fill: grad)[Volt]]
  #v(2pt)
  #box(width: 112pt, height: 4pt, radius: 2pt, fill: grad)
  #v(14pt)
  #text(size: 23pt, fill: ink, weight: 500)[The EDA toolchain, as a #text(fill: brand, weight: 700)[reward function.]]
  #v(9pt)
  #text(size: 14pt, fill: sub)[RL for verifiable, manufacturable circuit design.]
]
#v(1.1fr)

// ============================================================================
// 2 — WHY IT'S HARD
// ============================================================================
#pagebreak()
#head("01", "Why it's hard", [One chip. Ten exact connections.])
#grid(columns: (1.45fr, 1fr), gutter: 20pt, align: horizon,
  panel[
    #pill("DATASHEET", cyan) #h(5pt) #text(size: 11pt, fill: sub, weight: 600)[Step-down regulator — typical application]
    #v(9pt)
    #set text(size: 11.5pt, fill: body)
    #grid(columns: (auto, 1fr), row-gutter: 5pt, column-gutter: 9pt,
      text(font: mono, fill: brand, weight: 700)[1], [#raw("C_IN") ≥ 10 µF within 2 mm of VIN→GND],
      text(font: mono, fill: brand, weight: 700)[2], [Bootstrap cap #raw("C_BST") 0.1 µF, SW→BST],
      text(font: mono, fill: brand, weight: 700)[3], [Divider sets #raw("V_OUT = 0.8·(1+R1/R2)")],
      text(font: mono, fill: brand, weight: 700)[4], [Catch Schottky SW→GND, *cathode to SW*],
      text(font: mono, fill: brand, weight: 700)[5], [Inductor on SW; #raw("C_OUT") on VOUT→GND],
      text(font: mono, fill: brand, weight: 700)[6], [EN pull-up to VIN; short FB trace],
    )
  ],
  [
    #stat("~10", "parts per IC")
    #v(12pt)
    #stat("1", "wrong part = a re-spin")
    #v(12pt)
    #align(center)[#pill("DAYS–WEEKS LOST", bad)]
  ],
)

// ============================================================================
// 3 — WHY AGENTS FAIL
// ============================================================================
#pagebreak()
#head("02", "Why agents fail", [Looks right. #text(fill: bad)[Doesn't build.]])
#grid(columns: (1.4fr, 1fr), gutter: 20pt, align: horizon,
  panel[
    #set text(size: 13.5pt, fill: body)
    #grid(columns: (auto, 1fr), row-gutter: 11pt, column-gutter: 10pt,
      text(fill: bad, weight: 800)[✗], [#raw("D1.1/D1.2") — LED pins are *A / K*],
      text(fill: bad, weight: 800)[✗], [USB-C #raw("CC2") floating — *won't enumerate*],
      text(fill: bad, weight: 800)[✗], [MCU #raw("VDD") — *0 decoupling caps*],
      text(fill: bad, weight: 800)[✗], [Buck — *no inductor, no catch diode*],
    )
  ],
  [
    #stat("0 / 5", "raw buck designs built")
    #v(16pt)
    #align(center)[#text(size: 16pt, fill: ink, weight: 700)[Plausible #text(fill: bad)[≠] buildable.]]
  ],
)

// ============================================================================
// 4 — THE SOLUTION
// ============================================================================
#pagebreak()
#head("03", "The solution", [The toolchain becomes the #text(fill: brand)[reward].])
#grid(columns: (1fr, 1.3fr), gutter: 20pt, align: horizon,
  [
    #chip("Prompt")#h(3pt)#arr#h(3pt)#chip("DSL", c: brand2)#h(3pt)#arr#h(3pt)#chip("Real KiCad", c: brand2)
    #v(7pt)
    #chip("ERC + validators", c: brand2)#h(3pt)#arr#h(3pt)#chip("Reward 0–1")
    #v(16pt)
    #tags("Deterministic compile", "ERC + validators", "One 0–1 reward", "31 tasks")
  ],
  [#shot("assets/demo_schematic.png", 8.0cm)
   #v(5pt) #align(center)[#pill("ERC: 0 ERRORS", good) #h(4pt) #pill("REWARD 12.26 / 12.5", brand)]],
)

// ============================================================================
// 5 — THE LEARNING LOOP
// ============================================================================
#pagebreak()
#head("04", "The learning loop", [GRPO turns verification into #text(fill: brand)[improvement].])
#grid(columns: (1fr, 1fr), gutter: 20pt, align: horizon,
  [
    #tags("Reward only what passes", "Within-group variance = gradient", "Graded by real KiCad", "Qwen3-8B on HUD")
    #v(18pt)
    #grid(columns: (1fr, 1fr), stat("8", "reward dimensions"), stat("98%", "of max on passes"))
  ],
  panel[
    #pill("REWARD BREAKDOWN", brand) #h(5pt) #text(size: 11pt, fill: sub, weight: 600)[one passing design]
    #v(11pt)
    #let bar(lab, frac, c: brand) = grid(columns: (2.9cm, 1fr), column-gutter: 8pt, align: (right+horizon, left+horizon),
      text(font: mono, size: 10.5pt, fill: sub)[#lab],
      box(width: 100%, fill: paper, radius: 3pt)[#box(width: frac*100%, height: 13pt, fill: c, radius: 3pt)])
    #stack(spacing: 8pt,
      bar("erc", 1.0), bar("electrical", 1.0), bar("completeness", 0.9, c: brand2),
      bar("graph", 0.96), bar("cost", 0.8, c: cyan), bar("availability", 0.97),
      bar("size", 0.62, c: cyan))
  ],
)

// ============================================================================
// 6 — IMPACT
// ============================================================================
#pagebreak()
#head("05", "The impact", [A sentence → a #text(fill: brand)[manufacturable board].])
#grid(columns: (1.3fr, 1fr), gutter: 20pt, align: horizon,
  [#shot("assets/demo_3d.png", 8.0cm)
   #v(5pt) #align(center)[#pill("SCHEMATIC → TRACE → 3D → SEND TO FAB", brand2)]],
  [
    #tags("Fewer re-spins", "Validated automation", "Next: PCB layout & routing")
    #v(20pt)
    #align(center)[#box(inset: (x: 15pt, y: 11pt), radius: 12pt, fill: grad)[
      #text(size: 18pt, weight: 800, fill: white)[Don't just look right — build.]]]
  ],
)
