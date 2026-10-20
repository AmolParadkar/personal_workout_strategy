// The browser's local date as YYYY-MM-DD. The server can't know the person's
// local day, so the website sends it (e.g. for water logs).
export function todayLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// "21 Oct" style, for plain dates from the API (parsed as local, so no day shift).
export function formatShortDate(isoDate: string): string {
  const [year, month, day] = isoDate.slice(0, 10).split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  });
}
