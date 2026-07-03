const matches = [
  { home: '英格兰', away: '刚果(金)', oddsHome: 1.17, oddsDraw: 5.13, oddsAway: 12.50, handicap: 1 },
  { home: '比利时', away: '塞内加尔', oddsHome: 1.95, oddsDraw: 2.98, oddsAway: 3.56, handicap: 1 },
  { home: '美国', away: '波黑', oddsHome: 1.22, oddsDraw: 4.91, oddsAway: 9.40, handicap: 1 },
];

for (const m of matches) {
  const r = await fetch("http://localhost:3000/api/predict/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      home: m.home, away: m.away,
      oddsHome: m.oddsHome, oddsDraw: m.oddsDraw, oddsAway: m.oddsAway,
      handicap: -m.handicap,
      isKnockout: true,
      useAI: true
    })
  });
  const d = await r.json();
  console.log(`\n${'='.repeat(60)}`);
  console.log(`${m.home} vs ${m.away}`);
  console.log(`赔率: ${m.oddsHome}/${m.oddsDraw}/${m.oddsAway} | 让球: -${m.handicap}`);
  console.log(`融合: ${d.fusion.winPct}%/${d.fusion.drawPct}%/${d.fusion.awayPct}%`);
  console.log(`Top5: ${d.fusion.top5.slice(0,5).map(s=>s.score+'('+s.pct+'%)').join(', ')}`);
  if (d.aiReport && d.aiReport.report) {
    console.log(d.aiReport.report);
  }
  console.log('---');
}
