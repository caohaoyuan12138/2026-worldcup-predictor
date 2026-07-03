const r = await fetch("http://localhost:3000/api/status");
const d = await r.json();
console.log("completed:", d.stats.total);
console.log("teams:", d.teamCount);
