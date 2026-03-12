import { getStoredThemePreference } from '../context/ThemeContext';

export const READER_SETTINGS_STORAGE_KEY = 'readerSettings';

export const VOICES = {
    'American English (Female)': [
        'af_alloy', 'af_aoede', 'af_bella', 'af_heart', 'af_jessica',
        'af_kore', 'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky',
    ],
    'American English (Male)': [
        'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam',
        'am_michael', 'am_onyx', 'am_puck', 'am_santa',
    ],
    'British English (Female)': [
        'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily',
    ],
    'British English (Male)': [
        'bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis',
    ],
};

export const DEFAULT_SETTINGS = {
    fontSize: 18,
    fontFamily: 'Merriweather, Georgia, serif',
    theme: 'light',
    voice: 'af_heart',
    ttsSpeed: 1.0,
};

export const FONTS = [
    { value: 'Merriweather, Georgia, serif', label: 'Merriweather' },
    { value: 'Lora, Georgia, serif', label: 'Lora' },
    { value: 'Cormorant Garamond, Georgia, serif', label: 'Cormorant Garamond' },
    { value: 'Plus Jakarta Sans, Inter, system-ui, sans-serif', label: 'Plus Jakarta Sans' },
    { value: 'Manrope, Inter, system-ui, sans-serif', label: 'Manrope' },
    { value: 'Space Grotesk, Inter, system-ui, sans-serif', label: 'Space Grotesk' },
    { value: 'Inter, system-ui, sans-serif', label: 'Inter (Sans)' },
    { value: 'Georgia, serif', label: 'Georgia (Classic Serif)' },
    { value: 'system-ui, sans-serif', label: 'System Default' },
];

export function getSettings() {
    try {
        const saved = localStorage.getItem(READER_SETTINGS_STORAGE_KEY);
        const parsed = saved ? JSON.parse(saved) : {};
        return {
            ...DEFAULT_SETTINGS,
            ...parsed,
            theme: getStoredThemePreference(),
        };
    } catch {
        return {
            ...DEFAULT_SETTINGS,
            theme: getStoredThemePreference(),
        };
    }
}

export function saveReaderSettings(settings) {
    const { theme: _theme, ...readerSettings } = settings;
    localStorage.setItem(READER_SETTINGS_STORAGE_KEY, JSON.stringify(readerSettings));
    return {
        ...DEFAULT_SETTINGS,
        ...readerSettings,
        theme: settings.theme ?? getStoredThemePreference(),
    };
}