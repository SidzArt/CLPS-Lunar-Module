export function formatLatLon(lat: number, lon: number): string {
  const latHem = lat >= 0 ? "N" : "S";
  const lonHem = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(3)}° ${latHem}, ${Math.abs(lon).toFixed(3)}° ${lonHem}`;
}

export function formatElevation(elevM: number | null | undefined): string {
  if (elevM === null || elevM === undefined || Number.isNaN(elevM)) {
    return "Not recorded";
  }
  return `${elevM.toFixed(1)} m`;
}

export function formatNumber(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(decimals);
}

export function formatUtcTimestamp(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 120) {
    return `${seconds.toFixed(0)} s`;
  }
  if (seconds < 7200) {
    return `${(seconds / 60).toFixed(1)} min`;
  }
  const hours = seconds / 3600;
  if (hours < 48) {
    return `${hours.toFixed(1)} hr`;
  }
  return `${(hours / 24).toFixed(2)} days`;
}

