import { useState, useEffect } from 'react';
import { X, Type, Palette, Volume2 } from 'lucide-react';
import { getVoices } from '../../services/api';
import './SettingsPanel.css';

const FONT_FAMILIES = [
    { value: 'Georgia', label: 'Georgia (Serif)' },
    { value: 'Merriweather', label: 'Merriweather' },
    { value: 'Inter', label: 'Inter (Sans)' },
    { value: 'Roboto', label: 'Roboto' },
    { value: 'OpenDyslexic', label: 'OpenDyslexic' },
];

const FONT_SIZES = [14, 16, 18, 20, 22, 24, 28];

const THEMES = [
    { name: 'Dark', bg: '#0a0a0f', text: '#ffffff' },
    { name: 'Sepia', bg: '#f4ecd8', text: '#5c4b37' },
    { name: 'Light', bg: '#ffffff', text: '#1a1a2e' },
    { name: 'Night', bg: '#000000', text: '#b3b3b3' },
];

function SettingsPanel({ isOpen, onClose, settings, onSettingsChange }) {
    const [voices, setVoices] = useState({});
    const [activeTab, setActiveTab] = useState('text');

    useEffect(() => {
        loadVoices();
    }, []);

    const loadVoices = async () => {
        try {
            const voiceData = await getVoices();
            setVoices(voiceData);
        } catch (err) {
            console.error('Failed to load voices:', err);
        }
    };

    const updateSetting = (key, value) => {
        onSettingsChange({ ...settings, [key]: value });
    };

    if (!isOpen) return null;

    return (
        <div className="settings-overlay" onClick={onClose}>
            <div className="settings-panel" onClick={e => e.stopPropagation()}>
                <header className="settings-header">
                    <h2>Settings</h2>
                    <button className="close-btn" onClick={onClose}>
                        <X size={20} />
                    </button>
                </header>

                <nav className="settings-tabs">
                    <button
                        className={`tab-btn ${activeTab === 'text' ? 'active' : ''}`}
                        onClick={() => setActiveTab('text')}
                    >
                        <Type size={18} />
                        Text
                    </button>
                    <button
                        className={`tab-btn ${activeTab === 'theme' ? 'active' : ''}`}
                        onClick={() => setActiveTab('theme')}
                    >
                        <Palette size={18} />
                        Theme
                    </button>
                    <button
                        className={`tab-btn ${activeTab === 'audio' ? 'active' : ''}`}
                        onClick={() => setActiveTab('audio')}
                    >
                        <Volume2 size={18} />
                        Audio
                    </button>
                </nav>

                <div className="settings-content">
                    {activeTab === 'text' && (
                        <div className="settings-section">
                            <div className="setting-group">
                                <label>Font Size</label>
                                <div className="font-size-selector">
                                    {FONT_SIZES.map(size => (
                                        <button
                                            key={size}
                                            className={`size-btn ${settings.fontSize === size ? 'active' : ''}`}
                                            onClick={() => updateSetting('fontSize', size)}
                                        >
                                            {size}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="setting-group">
                                <label>Font Family</label>
                                <select
                                    className="input"
                                    value={settings.fontFamily}
                                    onChange={(e) => updateSetting('fontFamily', e.target.value)}
                                >
                                    {FONT_FAMILIES.map(font => (
                                        <option key={font.value} value={font.value}>
                                            {font.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="setting-group">
                                <label>Line Height</label>
                                <input
                                    type="range"
                                    min="1.4"
                                    max="2.4"
                                    step="0.1"
                                    value={settings.lineHeight || 1.9}
                                    onChange={(e) => updateSetting('lineHeight', parseFloat(e.target.value))}
                                />
                                <span className="range-value">{settings.lineHeight || 1.9}</span>
                            </div>
                        </div>
                    )}

                    {activeTab === 'theme' && (
                        <div className="settings-section">
                            <div className="setting-group">
                                <label>Color Theme</label>
                                <div className="theme-selector">
                                    {THEMES.map(theme => (
                                        <button
                                            key={theme.name}
                                            className={`theme-btn ${settings.bgColor === theme.bg ? 'active' : ''}`}
                                            style={{
                                                backgroundColor: theme.bg,
                                                color: theme.text,
                                                border: `2px solid ${settings.bgColor === theme.bg ? 'var(--accent-primary)' : theme.bg}`
                                            }}
                                            onClick={() => {
                                                updateSetting('bgColor', theme.bg);
                                                updateSetting('textColor', theme.text);
                                            }}
                                        >
                                            {theme.name}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'audio' && (
                        <div className="settings-section">
                            <div className="setting-group">
                                <label>TTS Voice</label>
                                <select
                                    className="input"
                                    value={settings.ttsVoice}
                                    onChange={(e) => updateSetting('ttsVoice', e.target.value)}
                                >
                                    {Object.entries(voices).map(([language, voiceList]) => (
                                        <optgroup key={language} label={language}>
                                            {voiceList.map(voice => (
                                                <option key={voice} value={voice}>{voice}</option>
                                            ))}
                                        </optgroup>
                                    ))}
                                </select>
                            </div>

                            <div className="setting-group">
                                <label>Speech Speed</label>
                                <input
                                    type="range"
                                    min="0.5"
                                    max="2"
                                    step="0.1"
                                    value={settings.ttsSpeed || 1}
                                    onChange={(e) => updateSetting('ttsSpeed', parseFloat(e.target.value))}
                                />
                                <span className="range-value">{settings.ttsSpeed || 1}x</span>
                            </div>
                        </div>
                    )}
                </div>

                <div className="settings-preview">
                    <p style={{
                        fontSize: `${settings.fontSize}px`,
                        fontFamily: settings.fontFamily,
                        lineHeight: settings.lineHeight || 1.9,
                        color: settings.textColor,
                        backgroundColor: settings.bgColor,
                        padding: 'var(--space-md)',
                        borderRadius: 'var(--radius-md)'
                    }}>
                        The path of cultivation is cruel. It demands sacrifice. It demands blood.
                    </p>
                </div>
            </div>
        </div>
    );
}

export default SettingsPanel;
