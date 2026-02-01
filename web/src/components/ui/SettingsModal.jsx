import { useState, useEffect } from 'react';
import { X, Volume2, Type, Palette } from 'lucide-react';
import './SettingsModal.css';

// English voices from Kokoro TTS
const VOICES = {
    "American English (Female)": [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky"
    ],
    "American English (Male)": [
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa"
    ],
    "British English (Female)": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily"
    ],
    "British English (Male)": [
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis"
    ]
};

const DEFAULT_SETTINGS = {
    fontSize: 18,
    fontFamily: 'Georgia',
    theme: 'dark',
    voice: 'af_heart',
    ttsSpeed: 1.0
};

const FONTS = [
    { value: 'Georgia', label: 'Georgia (Serif)' },
    { value: 'Merriweather', label: 'Merriweather' },
    { value: 'Inter', label: 'Inter (Sans)' },
    { value: 'system-ui', label: 'System Default' }
];

export function getSettings() {
    try {
        const saved = localStorage.getItem('readerSettings');
        return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
        return DEFAULT_SETTINGS;
    }
}

function SettingsModal({ isOpen, onClose, onSettingsChange }) {
    const [settings, setSettings] = useState(getSettings);

    useEffect(() => {
        if (isOpen) {
            setSettings(getSettings());
        }
    }, [isOpen]);

    const updateSetting = (key, value) => {
        const newSettings = { ...settings, [key]: value };
        setSettings(newSettings);
        localStorage.setItem('readerSettings', JSON.stringify(newSettings));
        onSettingsChange?.(newSettings);
    };

    if (!isOpen) return null;

    return (
        <div className="settings-overlay" onClick={onClose}>
            <div className="settings-modal" onClick={e => e.stopPropagation()}>
                <header className="settings-header">
                    <h2>Reader Settings</h2>
                    <button className="btn btn-ghost btn-icon" onClick={onClose}>
                        <X size={20} />
                    </button>
                </header>

                <div className="settings-content">
                    {/* Font Size */}
                    <section className="settings-section">
                        <div className="settings-label">
                            <Type size={18} />
                            <span>Font Size</span>
                            <span className="settings-value">{settings.fontSize}px</span>
                        </div>
                        <input
                            type="range"
                            min="14"
                            max="28"
                            value={settings.fontSize}
                            onChange={e => updateSetting('fontSize', parseInt(e.target.value))}
                            className="settings-slider"
                        />
                    </section>

                    {/* Font Family */}
                    <section className="settings-section">
                        <div className="settings-label">
                            <Type size={18} />
                            <span>Font Family</span>
                        </div>
                        <select
                            value={settings.fontFamily}
                            onChange={e => updateSetting('fontFamily', e.target.value)}
                            className="settings-select"
                        >
                            {FONTS.map(font => (
                                <option key={font.value} value={font.value}>
                                    {font.label}
                                </option>
                            ))}
                        </select>
                    </section>

                    {/* Theme */}
                    <section className="settings-section">
                        <div className="settings-label">
                            <Palette size={18} />
                            <span>Theme</span>
                        </div>
                        <div className="theme-toggle">
                            <button
                                className={`theme-btn ${settings.theme === 'light' ? 'active' : ''}`}
                                onClick={() => updateSetting('theme', 'light')}
                            >
                                Light
                            </button>
                            <button
                                className={`theme-btn ${settings.theme === 'dark' ? 'active' : ''}`}
                                onClick={() => updateSetting('theme', 'dark')}
                            >
                                Dark
                            </button>
                        </div>
                    </section>

                    {/* TTS Voice */}
                    <section className="settings-section">
                        <div className="settings-label">
                            <Volume2 size={18} />
                            <span>TTS Voice</span>
                        </div>
                        <select
                            value={settings.voice}
                            onChange={e => updateSetting('voice', e.target.value)}
                            className="settings-select"
                        >
                            {Object.entries(VOICES).map(([group, voices]) => (
                                <optgroup key={group} label={group}>
                                    {voices.map(voice => (
                                        <option key={voice} value={voice}>
                                            {voice}
                                        </option>
                                    ))}
                                </optgroup>
                            ))}
                        </select>
                    </section>

                    {/* TTS Speed */}
                    <section className="settings-section">
                        <div className="settings-label">
                            <Volume2 size={18} />
                            <span>TTS Speed</span>
                            <span className="settings-value">{settings.ttsSpeed}x</span>
                        </div>
                        <input
                            type="range"
                            min="0.5"
                            max="2"
                            step="0.1"
                            value={settings.ttsSpeed}
                            onChange={e => updateSetting('ttsSpeed', parseFloat(e.target.value))}
                            className="settings-slider"
                        />
                    </section>
                </div>
            </div>
        </div>
    );
}

export default SettingsModal;
