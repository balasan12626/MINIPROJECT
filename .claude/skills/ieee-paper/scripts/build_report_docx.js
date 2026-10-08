// Word report: INDICON 2026 rejection reasons -> issues -> fixes (yes/no).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, BorderStyle, AlignmentType,
  ShadingType, HeadingLevel, VerticalAlign, PageOrientation,
} = require("docx");

const FONT = "Calibri";
const W = 15398 - 2 * 1080; // A4 landscape width minus margins = 13238
const b = { style: BorderStyle.SINGLE, size: 4, color: "8C8C8C" };
const borders = { top: b, bottom: b, left: b, right: b };
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: 20, ...o });
const p = (children, o = {}) => new Paragraph({ spacing: { after: 120 }, ...o, children: Array.isArray(children) ? children : [children] });

function cell(text, width, o = {}) {
  const fill = o.fill;
  return new TableCell({
    width: { size: width, type: WidthType.DXA }, borders, verticalAlign: VerticalAlign.CENTER,
    shading: fill ? { type: ShadingType.CLEAR, color: "auto", fill } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ alignment: o.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [t(text, { bold: !!o.bold, color: o.color })] })],
  });
}
const WID = [500, 3000, 3300, 4938, 1500]; // sums to 13238
function issueTable(rows) {
  const head = new TableRow({ tableHeader: true, children: ["#", "Issue in old paper", "Why it is a problem", "What was fixed in the new paper", "Fixed?"]
    .map((h, i) => cell(h, WID[i], { bold: true, fill: "1F3864", color: "FFFFFF", center: i === 0 || i === 4 })) });
  const body = rows.map((r, k) => new TableRow({ children: [
    cell(String(r[0]), WID[0], { center: true, fill: k % 2 ? "F2F2F2" : undefined }),
    cell(r[1], WID[1], { fill: k % 2 ? "F2F2F2" : undefined }),
    cell(r[2], WID[2], { fill: k % 2 ? "F2F2F2" : undefined }),
    cell(r[3], WID[3], { fill: k % 2 ? "F2F2F2" : undefined }),
    cell(r[4] ? "YES" : "NO", WID[4], { bold: true, center: true, fill: r[4] ? "C6EFCE" : "FFC7CE", color: r[4] ? "006100" : "9C0006" }),
  ] }));
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: WID, rows: [head, ...body] });
}
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 120 }, children: [new TextRun({ text, font: FONT, size: 28, bold: true, color: "1F3864" })] });

const R1 = [
  [1, "Claimed PPO, quantum QAOA and SHAP", "The code does not train PPO, does not run a quantum circuit, and its route explanation is not SHAP. Claims bigger than the evidence look weak to reviewers.", "Paper now describes exactly what the code does: an adaptive route proposer, a QUBO solved classically, and attribution plus constraint traces. No quantum speed-up is claimed.", true],
  [2, "No single clear new idea", "Many buzzwords, but the main contribution was not clear.", "One clear idea: a fail-closed pipeline (hands control to a human when unsure) with a constraint shield after a learned route proposer.", true],
  [3, "Not compared with similar research", "Reviewers could not see what is new compared with existing work.", "Positioned against safe reinforcement learning and shielding research [4], [5], with 21 complete references.", true],
  [4, "Only claimed that the method is better", "A simple baseline (flood-aware A*) also reaches 100% safe routes in the code.", "Paper honestly reports that the shield matches A* but does not beat it. Reviewers trust honest results.", true],
  [5, "No real forecasting result", "No measured evidence that the system predicts floods.", "Real result on 49 unseen river gauges: balanced accuracy 0.898, ROC-AUC 0.965 vs 0.765 for the persistence baseline.", true],
  [6, "No new finding", "Nothing that other researchers could learn from.", "New finding: a mean-reliability safety gate misses most single-source failures (even a full weather-API outage).", true],
];
const R2 = [
  [7, "Author names, college and emails were on the paper", "INDICON uses double-blind review. Papers must not identify authors, or they can be rejected.", "Submission file shows only “Anonymous Author(s)”. Checked: no names, college, emails or file metadata.", true],
  [8, "Tables contained example numbers", "Text said the values “must be re-run before submission”. Fake numbers break research ethics.", "Every number comes from real, seeded runs of the project code (scripts included).", true],
  [9, "Incomplete references", "Missing journal, volume or pages (e.g. Farhi had no venue).", "21 complete IEEE-style references.", true],
  [10, "AI use not disclosed; file said “OpenAI Prism”", "IEEE requires disclosure of AI-generated content in the Acknowledgment.", "Honest AI disclosure added in the Acknowledgment; file metadata cleaned.", true],
  [11, "Page limit (4–6 pages)", "Papers over 6 pages are rejected.", "New paper is 5 pages.", true],
  [12, "IEEE format (2 columns, 10 pt Times, 8.5×11 in)", "Papers not following the template may be rejected without review.", "Built from the official IEEE template (LaTeX and Word versions).", true],
  [13, "PDF fonts", "IEEE Xplore needs all fonts embedded and no Type 3 fonts.", "Checked: 0 Type 3 fonts, 0 missing fonts.", true],
];
const R3 = [
  [14, "Spelling mistake in first word (“Disater”)", "Looks careless to reviewers.", "Corrected and re-checked.", true],
  [15, "Broken sentence in the abstract", "“In this paper, a hybrid … model that distinguishes …” has no verb.", "Abstract fully rewritten in clear sentences.", true],
  [16, "No architecture diagram", "Reviewers could not see how the system works.", "Fig. 1: system architecture diagram.", true],
  [17, "No results chart", "Results were hard to understand.", "Fig. 2: safe-route results chart.", true],
  [18, "Equations hard to read", "Symbols were broken or unclear.", "3 clean, numbered equations with every symbol explained.", true],
  [19, "Tables without explanation", "Numbers were given without discussion.", "3 clear tables, each explained in the text.", true],
  [20, "No limitations section", "Reviewers expect honest limits.", "New “Discussion and Limitations” section.", true],
  [21, "Uneven columns on last page", "Looks unfinished.", "Columns balanced.", true],
  [22, "Wording sounded machine-paraphrased", "Odd words (e.g. “detritus”) reduce clarity and trust.", "Rewritten in plain, natural academic English.", true],
];
const TODO = [
  ["A", "Confirm name spellings for the camera-ready file (Abhishek or ABISHAK? Gowthaman or GOWTHMAN?)"],
  ["B", "Confirm the students' department (Information Technology or AI & Data Science)"],
  ["C", "Supervisor (Nandhakumar T) must read and approve the paper"],
  ["D", "Check the next conference's own page limit, blind-review rule and PDF eXpress ID"],
];
const todoW = [800, 10438, 2000];
const todo = new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: todoW, rows: [
  new TableRow({ tableHeader: true, children: ["#", "Task for the authors", "Done?"].map((h, i) => cell(h, todoW[i], { bold: true, fill: "1F3864", color: "FFFFFF", center: i !== 1 })) }),
  ...TODO.map((r) => new TableRow({ children: [cell(r[0], todoW[0], { center: true }), cell(r[1], todoW[1]),
    cell("NO – authors only", todoW[2], { bold: true, center: true, fill: "FFEB9C", color: "9C5700" })] })),
] });

const folder = "D:\\fineal mini proejct\\1\\iee papper fineal\\revised\\";
const files = [
  ["SUBMIT_blind_review.pdf / .docx", "Upload this to the next conference (no author names)"],
  ["camera_ready_with_authors.pdf / .docx", "Use only after acceptance (with author names)"],
  ["*.tex, fig_safety.pdf", "LaTeX source files"],
  ["exp.py, exp.json, style.py", "Scripts and data to reproduce the results"],
];
const fW = [5000, 8238];
const fileTable = new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: fW, rows: [
  new TableRow({ tableHeader: true, children: ["File", "Use"].map((h, i) => cell(h, fW[i], { bold: true, fill: "1F3864", color: "FFFFFF" })) }),
  ...files.map((r) => new TableRow({ children: [cell(r[0], fW[0], { bold: true }), cell(r[1], fW[1])] })),
] });

const doc = new Document({
  creator: "Authors", title: "INDICON 2026 Rejection – Issues and Fixes",
  styles: { default: { document: { run: { font: FONT, size: 20 } } } },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838, orientation: PageOrientation.LANDSCAPE }, margin: { top: 1000, bottom: 1000, left: 1080, right: 1080 } } },
    children: [
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "INDICON 2026 Rejection: Issues and Fixes", font: FONT, size: 36, bold: true, color: "1F3864" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: [t("Paper 4244 – “Hybrid Quantum Reinforcement Learning with Explainable AI for Dynamic Disaster Evacuation Route Optimization”", { italics: true })] }),
      p([t("New title: ", { bold: true }), t("Fail-Closed Flood Evacuation Decision Support: Gauge-Held-Out Forecasting and a Constraint Shield for Learned Route Proposals")]),
      p([t("Summary: ", { bold: true }), t("22 issues found under the 3 rejection reasons. All 22 are fixed (YES). 4 tasks remain that only the authors can do. No paper can be guaranteed acceptance, but every listed reason has been addressed.")]),
      h1("Reason 1 – Limited novelty or insufficient originality"), issueTable(R1),
      h1("Reason 2 – Non-compliance with IEEE submission guidelines"), issueTable(R2),
      h1("Reason 3 – Technical presentation, organization or clarity"), issueTable(R3),
      h1("Still to do (authors only)"), todo,
      h1("File location"),
      p([t(folder, { bold: true })]),
      fileTable,
    ],
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync("INDICON_rejection_issues_and_fixes.docx", buf); console.log("ok"); });
