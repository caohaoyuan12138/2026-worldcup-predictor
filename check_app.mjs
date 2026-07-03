const b = await (await fetch("http://localhost:3000/app.js?v=3")).text();
const lines = b.split("\n");
console.log("Line 18-22:");
for (let i = 17; i < 22; i++) console.log((i + 1) + ": " + lines[i]);
console.log("---");
console.log("Has fusedLH?", b.includes("fusedLH"));
console.log("File size:", b.length);
