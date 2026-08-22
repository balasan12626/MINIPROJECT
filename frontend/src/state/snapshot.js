export function mergeSnapshot(prev, eventType, payload) {
  if (!prev) return prev;
  const next = { ...prev };
  if (eventType === "risk_update") next.prediction = payload;
  if (eventType === "weather_update") next.weather = payload;
  return next;
}
