import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { ExternalLink, Headphones, Library, Palette, Type, UserRound, Volume2, X } from 'lucide-react';
import { FONTS, VOICES } from '../../utils/readerSettings';
import { getAvatarUrl } from '../../utils/homeProfile';

function HomeProfilePanel({
    isOpen,
    onClose,
    profile,
    settings,
    audioHealth,
    audioHealthError,
    onProfileChange,
    onSettingChange,
}) {
    if (!isOpen) {
        return null;
    }

    const providerLabel = audioHealth?.provider === 'qwen3'
        ? 'Qwen3 local'
        : audioHealth?.provider === 'kokoro'
            ? 'Kokoro'
            : 'Provider unavailable';

    return (
        <AnimatePresence>
            <motion.div className="fixed inset-0 z-40 bg-black/35 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
            <motion.div className="fixed inset-4 z-50 flex items-start justify-center overflow-y-auto py-8" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>
                <div className="w-full max-w-3xl glass rounded-[32px] border border-white/45 dark:border-white/10 shadow-2xl overflow-hidden">
                    <div className="p-6 md:p-8 flex items-start justify-between gap-4 border-b border-stone-300/30 dark:border-white/8">
                        <div>
                            <p className="text-[10px] uppercase tracking-[0.2em] text-stone-500 dark:text-violet-300/60 font-semibold mb-2">Home profile</p>
                            <h2 className="text-2xl md:text-3xl font-bold text-stone-900 dark:text-white">{profile.displayName}'s settings</h2>
                            <p className="text-sm text-stone-600 dark:text-violet-200/70 mt-2 max-w-2xl">
                                Manage your local name, public credit link, and the shared reading and audio defaults used across the app.
                            </p>
                        </div>
                        <button type="button" onClick={onClose} className="w-10 h-10 rounded-full border border-stone-300/50 dark:border-violet-500/25 bg-white/45 dark:bg-violet-900/40 flex items-center justify-center text-stone-600 dark:text-violet-200 hover:text-stone-900 dark:hover:text-white hover:bg-white/70 dark:hover:bg-violet-500/15 transition-colors" aria-label="Close profile settings">
                            <X size={18} />
                        </button>
                    </div>

                    <div className="p-6 md:p-8 grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(260px,320px)]">
                        <div className="space-y-6">
                            <section className="rounded-[28px] glass-thin border border-white/45 dark:border-white/8 p-5 md:p-6">
                                <div className="flex items-center gap-3 mb-5">
                                    <div className="w-10 h-10 rounded-full bg-white/60 dark:bg-violet-900/40 border border-stone-300/50 dark:border-violet-500/20 flex items-center justify-center text-stone-700 dark:text-violet-200">
                                        <UserRound size={18} />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-semibold text-stone-900 dark:text-white">Profile</h3>
                                        <p className="text-sm text-stone-600 dark:text-violet-200/65">Stored locally on this machine.</p>
                                    </div>
                                </div>

                                <div className="grid gap-4 md:grid-cols-2">
                                    <label className="flex flex-col gap-2 md:col-span-2">
                                        <span className="text-sm font-semibold text-stone-700 dark:text-violet-100">Display name</span>
                                        <input className="input bg-white/50 dark:bg-violet-950/35 border-stone-300/50 dark:border-violet-500/20 text-stone-900 dark:text-white" type="text" value={profile.displayName} onChange={(event) => onProfileChange('displayName', event.target.value)} placeholder="Reader" />
                                    </label>

                                    <label className="flex flex-col gap-2 md:col-span-2">
                                        <span className="text-sm font-semibold text-stone-700 dark:text-violet-100">Public credit link</span>
                                        <input className="input bg-white/50 dark:bg-violet-950/35 border-stone-300/50 dark:border-violet-500/20 text-stone-900 dark:text-white" type="url" value={profile.creditUrl} onChange={(event) => onProfileChange('creditUrl', event.target.value)} placeholder="https://github.com/MohitRawat017/NovelLabs" />
                                    </label>
                                </div>
                            </section>

                            <section className="rounded-[28px] glass-thin border border-white/45 dark:border-white/8 p-5 md:p-6">
                                <div className="flex items-center gap-3 mb-5">
                                    <div className="w-10 h-10 rounded-full bg-white/60 dark:bg-violet-900/40 border border-stone-300/50 dark:border-violet-500/20 flex items-center justify-center text-stone-700 dark:text-violet-200">
                                        <Type size={18} />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-semibold text-stone-900 dark:text-white">Chapter settings</h3>
                                        <p className="text-sm text-stone-600 dark:text-violet-200/65">These match the reader settings modal.</p>
                                    </div>
                                </div>

                                <div className="space-y-5">
                                    <div>
                                        <div className="flex items-center gap-2 mb-2 text-sm font-semibold text-stone-700 dark:text-violet-100"><Palette size={16} /> Theme</div>
                                        <div className="flex gap-2">
                                            {['light', 'dark'].map((option) => (
                                                <button key={option} type="button" onClick={() => onSettingChange('theme', option)} className={`px-4 py-2 rounded-full border text-sm font-semibold transition-all ${settings.theme === option ? 'bg-stone-800 text-white border-stone-800 dark:bg-violet-500 dark:border-violet-400' : 'border-stone-300/60 dark:border-violet-500/25 text-stone-700 dark:text-violet-100 hover:bg-white/70 dark:hover:bg-violet-500/10'}`}>
                                                    {option[0].toUpperCase() + option.slice(1)}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    <div>
                                        <div className="flex items-center justify-between gap-2 mb-2 text-sm font-semibold text-stone-700 dark:text-violet-100"><span className="inline-flex items-center gap-2"><Type size={16} /> Font size</span><span>{settings.fontSize}px</span></div>
                                        <input type="range" min="14" max="28" value={settings.fontSize} onChange={(event) => onSettingChange('fontSize', parseInt(event.target.value, 10))} className="w-full accent-violet-500" />
                                    </div>

                                    <label className="flex flex-col gap-2">
                                        <span className="text-sm font-semibold text-stone-700 dark:text-violet-100">Font family</span>
                                        <select className="input bg-white/50 dark:bg-violet-950/35 border-stone-300/50 dark:border-violet-500/20 text-stone-900 dark:text-white" value={settings.fontFamily} onChange={(event) => onSettingChange('fontFamily', event.target.value)}>
                                            {FONTS.map((font) => <option key={font.value} value={font.value}>{font.label}</option>)}
                                        </select>
                                    </label>

                                    <label className="flex flex-col gap-2">
                                        <span className="text-sm font-semibold text-stone-700 dark:text-violet-100">TTS voice</span>
                                        <select className="input bg-white/50 dark:bg-violet-950/35 border-stone-300/50 dark:border-violet-500/20 text-stone-900 dark:text-white" value={settings.voice} onChange={(event) => onSettingChange('voice', event.target.value)}>
                                            {Object.entries(VOICES).map(([group, voices]) => (
                                                <optgroup key={group} label={group}>{voices.map((voice) => <option key={voice} value={voice}>{voice}</option>)}</optgroup>
                                            ))}
                                        </select>
                                    </label>

                                    <div>
                                        <div className="flex items-center justify-between gap-2 mb-2 text-sm font-semibold text-stone-700 dark:text-violet-100"><span className="inline-flex items-center gap-2"><Volume2 size={16} /> TTS speed</span><span>{settings.ttsSpeed}x</span></div>
                                        <input type="range" min="0.5" max="2" step="0.1" value={settings.ttsSpeed} onChange={(event) => onSettingChange('ttsSpeed', parseFloat(event.target.value))} className="w-full accent-violet-500" />
                                    </div>
                                </div>
                            </section>
                        </div>

                        <div className="space-y-6">
                            <section className="rounded-[28px] glass-thin border border-white/45 dark:border-white/8 p-5 md:p-6">
                                <div className="flex items-center gap-4">
                                    <div className="w-16 h-16 rounded-full overflow-hidden border border-stone-300/50 dark:border-violet-500/20 shadow-sm dark:shadow-glow-sm bg-white dark:bg-violet-950/40">
                                        <img src={getAvatarUrl(profile)} alt={`${profile.displayName} avatar`} className="w-full h-full object-cover" />
                                    </div>
                                    <div className="min-w-0">
                                        <h3 className="text-xl font-semibold text-stone-900 dark:text-white truncate">{profile.displayName}</h3>
                                        <p className="text-sm text-stone-600 dark:text-violet-200/65">Open-source credit link</p>
                                    </div>
                                </div>

                                <a href={profile.creditUrl} target="_blank" rel="noreferrer" className="mt-5 w-full rounded-full px-4 py-3 text-sm font-semibold border border-stone-300/50 dark:border-violet-500/25 text-stone-700 dark:text-violet-100 hover:bg-white/65 dark:hover:bg-violet-500/10 transition-all inline-flex items-center justify-center gap-2">
                                    <ExternalLink size={15} />
                                    View project link
                                </a>
                            </section>

                            <section className="rounded-[28px] glass-thin border border-white/45 dark:border-white/8 p-5 md:p-6">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="w-10 h-10 rounded-full bg-white/60 dark:bg-violet-900/40 border border-stone-300/50 dark:border-violet-500/20 flex items-center justify-center text-stone-700 dark:text-violet-200">
                                        <Headphones size={18} />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-semibold text-stone-900 dark:text-white">General audio reference</h3>
                                        <p className="text-sm text-stone-600 dark:text-violet-200/65">Backed by the current local audio provider.</p>
                                    </div>
                                </div>

                                <div className="space-y-3 text-sm">
                                    <div className="rounded-2xl bg-white/25 dark:bg-white/5 border border-white/55 dark:border-white/8 px-4 py-3">
                                        <p className="text-stone-500 dark:text-violet-300/60 uppercase tracking-[0.16em] text-[10px] font-semibold mb-1">Provider</p>
                                        <p className="font-semibold text-stone-800 dark:text-white">{providerLabel}</p>
                                    </div>
                                    <div className="rounded-2xl bg-white/25 dark:bg-white/5 border border-white/55 dark:border-white/8 px-4 py-3">
                                        <p className="text-stone-500 dark:text-violet-300/60 uppercase tracking-[0.16em] text-[10px] font-semibold mb-1">Defaults</p>
                                        <p className="font-semibold text-stone-800 dark:text-white">Voice: {settings.voice}</p>
                                        <p className="text-stone-600 dark:text-violet-200/65">Playback speed: {settings.ttsSpeed}x</p>
                                    </div>
                                    <div className="rounded-2xl bg-white/25 dark:bg-white/5 border border-white/55 dark:border-white/8 px-4 py-3">
                                        {audioHealth?.provider === 'qwen3' ? (
                                            <>
                                                <p className="font-semibold text-stone-800 dark:text-white mb-1">Qwen voices stay novel-specific.</p>
                                                <p className="text-stone-600 dark:text-violet-200/65 mb-3">Save cloned voice references from each novel page before queueing chapter audio.</p>
                                                <Link to="/library" className="inline-flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-violet-100 hover:text-stone-900 dark:hover:text-white">
                                                    <Library size={15} />
                                                    Open Library
                                                </Link>
                                            </>
                                        ) : (
                                            <>
                                                <p className="font-semibold text-stone-800 dark:text-white mb-1">Kokoro uses your shared reader defaults.</p>
                                                <p className="text-stone-600 dark:text-violet-200/65">Changing the voice or speed here affects the default Kokoro generation flow across the app.</p>
                                            </>
                                        )}
                                        {audioHealthError && <p className="text-xs text-rose-500 mt-3">{audioHealthError}</p>}
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                </div>
            </motion.div>
        </AnimatePresence>
    );
}

export default HomeProfilePanel;
