const b = await (await fetch("http://localhost:3000/app.js?v=BUILD202607011215")).text();
console.log("Has fusedLH?", b.includes("fusedLH"));
console.log("Has BUILD comment?", b.includes("BUILD: 2026-07-01T12:15"));
console.log("Size:", b.length);
// Check if app.js has any const/let before line 20 that could cause TDZ
const lines = b.split("\n");
for (let i = 0; i < 25; i++) {
  if (lines[i].trim().startsWith("const") || lines[i].trim().startsWith("let")) {
    console.log(`Line ${i+1}: ${lines[i].trim()}`);
  }
}
