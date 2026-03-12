import { useState, useEffect } from 'react';
import { X, Volume2, Type, Palette } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { FONTS, VOICES, getSettings, saveReaderSettings } from '../../utils/readerSettings';
import './SettingsModal.css';

export { getSettings } from '../../utils/readerSettings';

function SettingsModal({ isOpen, onClose, onSettingsChange }) {
    const { theme, setTheme } = useTheme();
    const [settings, setSettings] = useState(getSettings);

    useEffect(() => {
        if (isOpen) {
            setSettings(getSettings());
        }
    }, [isOpen]);

    useEffect(() => {
        setSettings((previous) => ({ ...previous, theme }));
    }, [theme]);

    const updateSetting = (key, value) => {
        const newSettings = { ...settings, [key]: value };
        setSettings(newSettings);

        if (key === 'theme') {
            setTheme(value);
        }

        saveReaderSettings(newSettings);
        onSettingsChange?.(newSettings);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 md:p-8 animate-in fade-in duration-200" onClick={onClose}>
            <div className="glass w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col rounded-[32px] border border-white/20 dark:border-white/10 shadow-2xl" onClick={e => e.stopPropagation()}>
                <header className="flex items-center justify-between p-6 border-b border-stone-200/50 dark:border-white/10 bg-white/40 dark:bg-black/20">
                    <h2 className="text-xl font-bold text-stone-900 dark:text-white mt-1">Reader Settings</h2>
                    <button 
                        className="w-10 h-10 rounded-full flex items-center justify-center bg-white/50 dark:bg-white/5 hover:bg-stone-200 dark:hover:bg-white/10 text-stone-700 dark:text-stone-300 transition-all border border-stone-200/50 dark:border-white/5" 
                        onClick={onClose}
                    >
                        <X size={20} />
                    </button>
                </header>

                <div className="p-6 overflow-y-auto flex flex-col gap-8 bg-white/60 dark:bg-background/40">
                    <section className="flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-stone-600 dark:text-stone-300 font-medium">
                            <Type size={18} className="text-violet-500" />
                            <span>Font Size</span>
                            <span className="ml-auto text-violet-600 dark:text-violet-400 font-bold">{settings.fontSize}px</span>
                        </div>
                        <input
                            type="range"
                            min="14"
                            max="28"
                            value={settings.fontSize}
                            onChange={e => updateSetting('fontSize', parseInt(e.target.value))}
                            className="w-full h-2 rounded-full appearance-none bg-stone-200 dark:bg-white/10 accent-violet-500 cursor-pointer"
                        />
                    </section>

                    <section className="flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-stone-600 dark:text-stone-300 font-medium">
                            <Type size={18} className="text-violet-500" />
                            <span>Font Family</span>
                        </div>
                        <select
                            value={settings.fontFamily}
                            onChange={e => updateSetting('fontFamily', e.target.value)}
                            className="w-full px-4 py-3 rounded-2xl glass-thin bg-white/70 dark:bg-black/40 border border-stone-200/50 dark:border-white/10 text-stone-800 dark:text-stone-200 outline-none focus:border-violet-500/50 appearance-none font-medium"
                        >
                            {FONTS.map(font => (
                                <option key={font.value} value={font.value} className="bg-white dark:bg-[#110e15] text-stone-800 dark:text-stone-200">
                                    {font.label}
                                </option>
                            ))}
                        </select>
                    </section>

                    <section className="flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-stone-600 dark:text-stone-300 font-medium">
                            <Palette size={18} className="text-violet-500" />
                            <span>Theme Base</span>
                        </div>
                        <div className="flex gap-2">
                            <button
                                className={`flex-1 py-3 rounded-2xl font-bold text-sm transition-all border ${settings.theme === 'light' ? 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white border-transparent shadow-md' : 'glass-thin bg-white/50 dark:bg-black/20 text-stone-600 dark:text-stone-400 border-stone-200/50 dark:border-white/10 hover:bg-white/80 dark:hover:bg-white/5'}`}
                                onClick={() => updateSetting('theme', 'light')}
                            >
                                Light
                            </button>
                            <button
                                className={`flex-1 py-3 rounded-2xl font-bold text-sm transition-all border ${settings.theme === 'dark' ? 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white border-transparent shadow-md' : 'glass-thin bg-white/50 dark:bg-black/20 text-stone-600 dark:text-stone-400 border-stone-200/50 dark:border-white/10 hover:bg-white/80 dark:hover:bg-white/5'}`}
                                onClick={() => updateSetting('theme', 'dark')}
                            >
                                Dark
                            </button>
                        </div>
                    </section>

                    <section className="flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-stone-600 dark:text-stone-300 font-medium">
                            <Volume2 size={18} className="text-violet-500" />
                            <span>TTS Voice</span>
                        </div>
                        <select
                            value={settings.voice}
                            onChange={e => updateSetting('voice', e.target.value)}
                            className="w-full px-4 py-3 rounded-2xl glass-thin bg-white/70 dark:bg-black/40 border border-stone-200/50 dark:border-white/10 text-stone-800 dark:text-stone-200 outline-none focus:border-violet-500/50 appearance-none font-medium"
                        >
                            {Object.entries(VOICES).map(([group, voices]) => (
                                <optgroup key={group} label={group} className="font-bold text-stone-500 dark:text-stone-400">
                                    {voices.map(voice => (
                                        <option key={voice} value={voice} className="bg-white dark:bg-[#110e15] font-normal text-stone-800 dark:text-stone-200">
                                            {voice}
                                        </option>
                                    ))}
                                </optgroup>
                            ))}
                        </select>
                    </section>

                    <section className="flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-stone-600 dark:text-stone-300 font-medium">
                            <Volume2 size={18} className="text-violet-500" />
                            <span>TTS Speed</span>
                            <span className="ml-auto text-violet-600 dark:text-violet-400 font-bold">{settings.ttsSpeed}x</span>
                        </div>
                        <input
                            type="range"
                            min="0.5"
                            max="2"
                            step="0.1"
                            value={settings.ttsSpeed}
                            onChange={e => updateSetting('ttsSpeed', parseFloat(e.target.value))}
                            className="w-full h-2 rounded-full appearance-none bg-stone-200 dark:bg-white/10 accent-violet-500 cursor-pointer"
                        />
                    </section>
                </div>
            </div>
        </div>
    );
}

export default SettingsModal;
