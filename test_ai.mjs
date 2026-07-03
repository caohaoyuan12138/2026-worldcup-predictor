try {
  const r = await fetch("http://localhost:3000/api/predict/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ home: "法国", away: "挪威", useAI: true })
  });
  const text = await r.text();
  console.log("Response (first 500 chars):", text.substring(0, 500));
} catch (e) {
  console.error(e.message);
}
