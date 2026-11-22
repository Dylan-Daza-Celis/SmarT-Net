// Empty URL selects same-origin (used by the isolated validation proxy).
export const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
