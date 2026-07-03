const r = await fetch('http://localhost:3000/api/predict/match', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ home: '法国', away: '挪威', isKnockout: true, useAI: false })
});
const d = await r.json();
console.log(JSON.stringify(d, null, 2));
