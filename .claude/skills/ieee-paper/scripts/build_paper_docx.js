// Build the IEEE conference paper as .docx (IEEE Word template layout: Letter, 2 columns, Times 10 pt).
// usage: node build_paper_docx.js <blind|camera> <out.docx>
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, TabStopType, SectionType, LevelFormat, VerticalAlign,
} = require("docx");

const mode = process.argv[2] || "blind";
const outFile = process.argv[3] || `paper_${mode}.docx`;
const P = JSON.parse(fs.readFileSync("paper.json", "utf8"));
const FONT = "Times New Roman";
const COL = 5040; // 3.5 in column
const IND = 288;  // 14.4 pt first-line indent (IEEE template)

// math runs: "x_k" -> subscript, "e^(...)" -> superscript
function mathRuns(t, size, extra) {
  const out = [];
  const re = /_([A-Za-z0-9]+)|\^\(([^()]*(?:\([^()]*\))?[^()]*)\)/g;
  let last = 0, m;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(new TextRun({ text: t.slice(last, m.index), italics: true, font: FONT, size, ...extra }));
    if (m[1] !== undefined) out.push(new TextRun({ text: m[1], italics: true, subScript: true, font: FONT, size, ...extra }));
    else out.push(new TextRun({ text: m[2], italics: true, superScript: true, font: FONT, size, ...extra }));
    last = re.lastIndex;
  }
  if (last < t.length) out.push(new TextRun({ text: t.slice(last), italics: true, font: FONT, size, ...extra }));
  return out;
}
const isMath = (t) => /[_^=<>≤≥∈±·]/.test(t) || /^[A-Za-z]$/.test(t.trim());
const runs = (rs, size = 20, extra = {}) => rs.flatMap((r) =>
  r.i && isMath(r.t) ? mathRuns(r.t, size, extra) : [new TextRun({ text: r.t, italics: !!r.i, font: FONT, size, ...extra })]);
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
const img = (file, w, h) => new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: w, height: h } });

// ---------------------------------------------------------------- tables
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const rule = (sz) => ({ style: BorderStyle.SINGLE, size: sz, color: "000000" });
function dataTable(head, rows, widths, note) {
  const total = widths.reduce((a, b) => a + b, 0);
  const mk = (cells, i, isHead, isLast) => new TableRow({
    tableHeader: isHead,
    children: cells.map((c, j) => new TableCell({
      width: { size: widths[j], type: WidthType.DXA },
      margins: { top: 20, bottom: 20, left: 30, right: 30 },
      borders: {
        top: isHead ? rule(8) : none, bottom: isHead || isLast ? rule(isLast ? 8 : 4) : none,
        left: none, right: none,
      },
      children: [new Paragraph({
        alignment: j === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
        children: [new TextRun({ text: String(c).replace(/^\*(.*)\*$/, "$1"), bold: /^\*.*\*$/.test(String(c)), font: FONT, size: 16 })],
      })],
    })),
  });
  const t = new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths, alignment: AlignmentType.CENTER,
    rows: [mk(head, 0, true, false), ...rows.map((r, i) => mk(r, i + 1, false, i === rows.length - 1))],
  });
  const out = [t];
  if (note) out.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: note, font: FONT, size: 14 })] }));
  else out.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
  return out;
}
const tcap = (n, text) => [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, keepNext: true,
    children: [new TextRun({ text: `TABLE ${n}`, font: FONT, size: 16, smallCaps: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, keepNext: true,
    children: [new TextRun({ text, font: FONT, size: 16, smallCaps: true })] }),
];
const fcap = (n, text) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { before: 60, after: 160 },
  children: [new TextRun({ text: `Fig. ${n}.  `, font: FONT, size: 16 }), new TextRun({ text, font: FONT, size: 16 })],
});
// figure scaled to width w (px at 96 dpi), height from the PNG's aspect ratio
const figPara = (file, w) => {
  const b = fs.readFileSync(file);
  const h = Math.round((w * b.readUInt32BE(20)) / b.readUInt32BE(16));
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, keepNext: true, children: [img(file, w, h)] });
};

const FLOATS = {
  "fig:arch": () => [figPara("img/arch.png", 336),
    fcap(1, "Fail-closed pipeline. Shaded blocks can stop or downgrade automation. The dashed link carries source reliability and health checks to the policy. Every block writes to the audit log.")],
  "fig:stress": () => [figPara("img/safety.png", 331),
    fcap(4, "Safe-route rate as initial road closures increase (30 seeded scenarios per bar).")],
  "tab:thr": () => [...tcap("III", "Operating points on the test set (threshold 0.45 set on validation)"),
    ...dataTable(["Threshold", "Recall", "Precision", "Alarms / 1000 days"], [["0.30", "0.942", "0.261", "197.2"], ["0.45", "0.902", "0.328", "150.2"], ["0.60", "0.845", "0.413", "111.6"], ["0.75", "0.760", "0.539", "77.0"]], [900, 900, 900, 1500])],
  "tab:shield": () => [...tcap("VI", "Shield trace for one scenario (seed 93)"),
    ...dataTable(["Rank", "Route", "Time (min)", "Hazard", "Shield"], [["1", "Z1 → A → B → SA", "16.7", "0.147", "rejected: capacity"], ["2", "Z1 → A → B → E → F → SB", "23.1", "0.147", "selected"], ["3", "Z1 → A → D → E → F → SB", "23.5", "0.206", "feasible"]], [500, 2000, 800, 700, 1200])],
  "fig:curves": () => [figPara("img/curves.png", 331), fcap(2, "Precision–recall (left) and ROC (right) curves on the 48 unseen test gauges. The square is persistence; the dotted line on the left is the flood rate.")],
  "fig:gauges": () => [figPara("img/gauges.png", 331), fcap(3, "Balanced accuracy of each unseen gauge with at least one flood window (46 gauges). The dashed line is the median.")],
  "tab:fc": () => [...tcap("I", "Three-day exceedance forecasting on 48 unseen gauges, 2015–2020"),
    ...dataTable(["Method", "BA", "Recall", "Prec.", "F1", "ROC-AUC", "PR-AUC"], [
      ["Persistence", "0.765", "0.538", "*0.789*", "*0.640*", "0.765", "0.449"],
      ["XGBoost (all days)", "*0.898*", "*0.902*", "0.328", "0.481", "*0.965*", "*0.737*"],
      ["XGBoost (onsets)", "0.857", "0.813", "0.177", "0.290", "0.940", "0.369"],
    ], [1440, 560, 600, 560, 520, 700, 660], "BA = balanced accuracy; threshold 0.45 (set on validation); n = 52,994.")],
  "tab:val": () => [...tcap("II", "Validation results of the seven candidates (2009–2014, n = 349,645)"),
    ...dataTable(["Model", "Rows", "BA", "Recall", "Prec.", "PR-AUC"], [
      ["Logistic regression", "sub", "0.899", "0.916", "0.391", "0.751"],
      ["Random forest", "sub", "0.905", "0.924", "0.403", "0.781"],
      ["Hist. gradient boosting", "full", "0.909", "0.930", "0.408", "0.791"],
      ["XGBoost, depth 4", "full", "0.909", "0.934", "0.401", "0.790"],
      ["XGBoost, depth 6 (earlier fit)", "full", "0.909", "0.925", "0.420", "0.792"],
      ["XGBoost, depth 8", "full", "0.909", "0.927", "0.416", "0.793"],
      ["XGBoost, depth 6 (selected)", "full", "*0.911*", "*0.936*", "0.404", "*0.796*"],
    ], [1900, 520, 560, 600, 560, 660], "sub = 500,000-row training subsample; full = all 1,641,197 training rows.")],
  "tab:route": () => [...tcap("IV", "Routing benchmark, 30 seeded scenarios (mean ± s.d.)"),
    ...dataTable(["Method", "Safe (%)", "Clear. (min)", "Cap. viol.", "Re-plan (ms)"], [
      ["Static shortest path", "90.0 ± 20.0", "16.63", "0.20", "0.19"],
      ["Flood-aware A*", "100.0 ± 0.0", "17.81", "0.00", "0.17"],
      ["Risk-aware greedy", "90.0 ± 20.0", "16.63", "0.20", "1.22"],
      ["Proposer only", "90.0 ± 20.0", "16.63", "0.20", "2.50"],
      ["Proposer + shield (SA)", "100.0 ± 0.0", "17.81", "0.00", "2.68"],
      ["Proposer + shield (QI)", "100.0 ± 0.0", "17.82", "0.00", "3.00"],
    ], [1600, 900, 860, 760, 920], "SA = simulated annealing; QI = QAOA-inspired classical sampler.")],
  "tab:sweep": () => [...tcap("V", "Safe-route rate (%) and travel time (min) against initial closures (flood severity 0.35, 30 scenarios each)"),
    ...dataTable(["Method", "Safe 0", "Time 0", "Safe 2", "Time 2", "Safe 4", "Time 4"], [
      ["Static shortest path", "90.00", "16.63", "93.33", "18.50", "86.67", "24.46"],
      ["Flood-aware A*", "100.00", "17.81", "100.00", "19.31", "93.33", "25.28"],
      ["Risk-aware greedy", "90.00", "16.63", "93.33", "18.50", "86.67", "24.46"],
      ["Proposer only", "90.00", "16.63", "86.67", "19.07", "68.33", "20.47"],
      ["Proposer + shield (SA)", "100.00", "17.81", "100.00", "19.31", "93.33", "25.27"],
      ["Proposer + shield (QI)", "100.00", "17.82", "100.00", "19.32", "93.33", "25.28"],
    ], [1500, 560, 560, 560, 560, 560, 560], "Columns give the number of initial closures.")],
  "tab:gate": () => [...tcap("VII", "Failure injection: mean-based (deployed) and minimum-based gates, threshold 0.60"),
    ...dataTable(["Injected failure", "Mean rel.", "Mean gate", "Min rel.", "Min gate"], [
      ["None", "0.810", "allowed", "0.600", "allowed"],
      ["Weather API outage", "0.662", "allowed", "0.200", "*blocked*"],
      ["Delayed radar", "0.744", "allowed", "0.550", "*blocked*"],
      ["Flood-sensor drift", "0.724", "allowed", "0.480", "*blocked*"],
      ["Stale road database", "0.746", "allowed", "0.400", "*blocked*"],
      ["Conflicting citizen reports", "0.780", "allowed", "0.450", "*blocked*"],
      ["Shelter failure", "0.810", "allowed", "0.600", "allowed"],
      ["Communications failure", "0.586", "*blocked*", "0.350", "*blocked*"],
      ["Delayed radar + sensor drift", "0.658", "allowed", "0.480", "*blocked*"],
      ["Sensor drift + stale roads", "0.660", "allowed", "0.400", "*blocked*"],
      ["Weather + drift + stale roads", "0.512", "*blocked*", "0.200", "*blocked*"],
    ], [2200, 700, 760, 700, 760], "Shelter failure affects capacity, not a data source, and is handled by the shield.")],
};
const pngSize = (f) => { const b = fs.readFileSync(f); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };
const EQS = { "eq:target": ["img/eq1.png", 1], "eq:risk": ["img/eq2.png", 2], "eq:qubo": ["img/eq3.png", 3],
  "eq:ba": ["img/eq4.png", 4], "eq:safe": ["img/eq5.png", 5] };
const eqPara = (id) => {
  const [f, n] = EQS[id];
  const [w, h] = pngSize(f);
  const k = 96 / 600; // 600 dpi render -> natural size
  return new Paragraph({
    tabStops: [{ type: TabStopType.CENTER, position: COL / 2 }, { type: TabStopType.RIGHT, position: COL }],
    spacing: { before: 80, after: 80 },
    children: [new TextRun({ text: "\t", font: FONT }), img(f, Math.round(w * k), Math.round(h * k)),
      new TextRun({ text: `\t(${n})`, font: FONT, size: 20 })],
  });
};

// ---------------------------------------------------------------- front matter
const front = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [new TextRun({ text: P.title, font: FONT, size: 48 })] }),
];
const authors = [
  ["Nandhakumar T", "Department of Information Technology", "nandhakumartm93@gmail.com"],
  ["Balakarthikeyan B S", "Department of Artificial Intelligence and Data Science", "balasan2626@gmail.com"],
  ["Gowthaman J", "Department of Artificial Intelligence and Data Science", "gowthamanjanadhran@gmail.com"],
  ["Abhishek S", "Department of Artificial Intelligence and Data Science", "abisheksengodan18@gmail.com"],
];
const authorCell = (a) => new TableCell({
  width: { size: 5220, type: WidthType.DXA }, borders: { top: none, bottom: none, left: none, right: none },
  margins: { top: 40, bottom: 120 },
  children: [
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: a[0], font: FONT, size: 22 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: a[1], font: FONT, size: 20, italics: true })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Sona College of Technology", font: FONT, size: 20, italics: true })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Salem, Tamil Nadu, India", font: FONT, size: 20 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: a[2], font: FONT, size: 20 })] }),
  ],
});
if (mode === "camera") {
  front.push(new Table({
    width: { size: 10440, type: WidthType.DXA }, columnWidths: [5220, 5220],
    rows: [new TableRow({ children: [authorCell(authors[0]), authorCell(authors[1])] }),
      new TableRow({ children: [authorCell(authors[2]), authorCell(authors[3])] })],
  }));
} else {
  front.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Anonymous Author(s)", font: FONT, size: 22 })] }));
  front.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [new TextRun({ text: "Affiliation withheld for double-blind review", font: FONT, size: 20, italics: true })] }));
}

// ---------------------------------------------------------------- body
const body = [
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, indent: { firstLine: IND }, spacing: { after: 120 },
    children: [new TextRun({ text: "Abstract", font: FONT, size: 18, bold: true, italics: true }),
      new TextRun({ text: "—", font: FONT, size: 18, bold: true }), ...runs(P.abstract, 18, { bold: true })] }),
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, indent: { firstLine: IND }, spacing: { after: 160 },
    children: [new TextRun({ text: "Keywords", font: FONT, size: 18, bold: true, italics: true }),
      new TextRun({ text: "—" + P.keywords, font: FONT, size: 18, bold: true })] }),
];
let h1 = 0, h2 = 0;
for (const b of P.blocks) {
  if (b.type === "h1") {
    const numbered = b.text !== "Acknowledgment";
    if (numbered) { h1 += 1; h2 = 0; }
    body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
      children: [new TextRun({ text: (numbered ? ROMAN[h1 - 1] + ". " : "") + b.text, font: FONT, size: 20, smallCaps: true })] }));
  } else if (b.type === "h2") {
    h2 += 1;
    body.push(new Paragraph({ spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new TextRun({ text: String.fromCharCode(64 + h2) + ". " + b.text, font: FONT, size: 20, italics: true })] }));
  } else if (b.type === "p") {
    body.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, indent: b.noindent ? undefined : { firstLine: IND },
      children: runs(b.runs) }));
  } else if (b.type === "li") {
    body.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, numbering: { reference: "contrib", level: 0 },
      children: runs(b.runs) }));
  } else if (b.type === "float") {
    body.push(...FLOATS[b.id]());
  } else if (b.type === "eq") {
    body.push(eqPara(b.id));
  }
}
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 },
  children: [new TextRun({ text: "References", font: FONT, size: 20, smallCaps: true })] }));
P.refs.forEach((r, i) => body.push(new Paragraph({
  alignment: AlignmentType.JUSTIFIED, indent: { left: 360, hanging: 360 }, spacing: { after: 20 },
  tabStops: [{ type: TabStopType.LEFT, position: 360 }],
  children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 16 }), ...runs(r, 16)],
})));

const page = { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1440, left: 900, right: 900 } };
const doc = new Document({
  creator: mode === "camera" ? "Authors" : "Anonymous",
  title: P.title,
  styles: { default: { document: { run: { font: FONT, size: 20 }, paragraph: { spacing: { line: 240 } } } } },
  numbering: { config: [{ reference: "contrib", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1)",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 270 } } } }] }] },
  sections: [
    { properties: { page }, children: front },
    { properties: { page, type: SectionType.CONTINUOUS, column: { count: 2, space: 360, equalWidth: true } }, children: body },
  ],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(outFile, buf); console.log("wrote", outFile); });
