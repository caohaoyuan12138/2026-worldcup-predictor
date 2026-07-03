// 三场1/8决赛预测
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
      handicap: -m.handicap, // 用户输入-1=主队让1球, 引擎handicap=1
      isKnockout: true,
      useAI: false
    })
  });
  const d = await r.json();
  console.log(`\n=== ${m.home} vs ${m.away} ===`);
  console.log("融合胜率:", d.fusion.winPct + "/" + d.fusion.drawPct + "/" + d.fusion.awayPct);
  console.log("融合λ:", d.fusion.lambda.home.toFixed(2) + "/" + d.fusion.lambda.away.toFixed(2));
  console.log("Top5比分:", d.fusion.top5.slice(0,5).map(s => s.score + "(" + s.pct + "%)").join(", "));
  console.log("Elo:", d.models.elo.rating.home + "/" + d.models.elo.rating.away);
  console.log("赔率隐含:", d.models.market.odds.home + "/" + d.models.market.odds.draw + "/" + d.models.market.odds.away);
}
