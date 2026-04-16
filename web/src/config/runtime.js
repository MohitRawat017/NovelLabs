export const IS_READ_ONLY_MODE = String(import.meta.env.VITE_READ_ONLY_MODE || '')
    .trim()
    .toLowerCase() === 'true';
