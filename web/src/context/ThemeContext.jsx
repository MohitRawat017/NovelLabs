import { createContext, useContext, useEffect, useState } from 'react';

export const THEME_STORAGE_KEY = 'novellabs.app.theme';
const LEGACY_READER_SETTINGS_KEY = 'readerSettings';
const VALID_THEMES = new Set(['light', 'dark']);

function readLegacyTheme() {
    try {
        const rawSettings = localStorage.getItem(LEGACY_READER_SETTINGS_KEY);
        if (!rawSettings) {
            return null;
        }

        const parsed = JSON.parse(rawSettings);
        return VALID_THEMES.has(parsed?.theme) ? parsed.theme : null;
    } catch {
        return null;
    }
}

function getSystemTheme() {
    if (typeof window === 'undefined' || !window.matchMedia) {
        return 'light';
    }

    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function getStoredThemePreference() {
    if (typeof window === 'undefined') {
        return 'light';
    }

    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    if (VALID_THEMES.has(storedTheme)) {
        return storedTheme;
    }

    return readLegacyTheme() || getSystemTheme();
}

function applyThemeToDocument(theme) {
    if (typeof document === 'undefined') {
        return;
    }

    if (theme === 'dark') {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }

    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.body.dataset.theme = theme;
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
    const [theme, setThemeState] = useState(getStoredThemePreference);

    useEffect(() => {
        applyThemeToDocument(theme);
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    }, [theme]);

    useEffect(() => {
        if (typeof window === 'undefined' || !window.matchMedia) {
            return undefined;
        }

        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        const handleThemeChange = () => {
            const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
            if (!VALID_THEMES.has(storedTheme)) {
                setThemeState(mediaQuery.matches ? 'dark' : 'light');
            }
        };

        mediaQuery.addEventListener('change', handleThemeChange);
        return () => mediaQuery.removeEventListener('change', handleThemeChange);
    }, []);

    const setTheme = (nextTheme) => {
        if (!VALID_THEMES.has(nextTheme)) {
            return;
        }
        setThemeState(nextTheme);
    };

    const toggleTheme = () => {
        setTheme(theme === 'light' ? 'dark' : 'light');
    };

    return (
        <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within ThemeProvider');
    }
    return context;
}
