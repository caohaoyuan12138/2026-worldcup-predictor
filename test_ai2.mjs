const r = await fetch("http://localhost:3000/api/predict/match", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ home: "法国", away: "挪威", useAI: true })
});
const d = await r.json();
console.log("has aiReport:", !!d.aiReport);
if (d.aiReport) {
  console.log("aiReport keys:", Object.keys(d.aiReport));
  if (d.aiReport.report) console.log("report preview:", d.aiReport.report.substring(0, 300));
  if (d.aiReport.error) console.log("aiReport.error:", d.aiReport.error);
}
