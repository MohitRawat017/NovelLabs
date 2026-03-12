import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, Download, Headphones, Library, Sparkles } from 'lucide-react';
import HomeProfilePanel from '../components/home/HomeProfilePanel';
import { useScrapingJobs } from '../context/ScrapingContext';
import { useTheme } from '../context/ThemeContext';
import { getHomeProfile, getAvatarUrl, saveHomeProfile } from '../utils/homeProfile';
import { getSettings, saveReaderSettings } from '../utils/readerSettings';
import { getAudioHealth, getNovels } from '../services/api';

function normalizeNovel(novel) {
    return {
        id: novel?.id ?? novel?.Id ?? null,
        slug: novel?.slug ?? novel?.Slug ?? '',
        title: novel?.title ?? novel?.Title ?? 'Untitled Novel',
        coverUrl: novel?.cover_url ?? novel?.CoverUrl ?? '',
        chapterCount: Number(novel?.chapter_count ?? novel?.chapterCount ?? novel?.Chapters?.length ?? 0),
        views: Number(novel?.views ?? novel?.Views ?? 0),
    };
}

function formatNumber(value) {
    return new Intl.NumberFormat().format(Number(value) || 0);
}

function Home() {
    const { jobs, audioJobs, activeJobCount, activeAudioJobCount, togglePanel } = useScrapingJobs();
    const { theme, setTheme } = useTheme();
    const [novels, setNovels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showProfilePanel, setShowProfilePanel] = useState(false);
    const [profile, setProfile] = useState(getHomeProfile);
    const [settings, setSettings] = useState(getSettings);
    const [audioHealth, setAudioHealth] = useState(null);
    const [audioHealthError, setAudioHealthError] = useState(null);

    useEffect(() => {
        const loadHomeData = async () => {
            try {
                const [novelsResult, audioHealthResult] = await Promise.allSettled([getNovels(), getAudioHealth()]);
                setNovels(novelsResult.status === 'fulfilled' && Array.isArray(novelsResult.value?.novels) ? novelsResult.value.novels : []);

                if (audioHealthResult.status === 'fulfilled') {
                    setAudioHealth(audioHealthResult.value);
                    setAudioHealthError(null);
                } else {
                    setAudioHealth(null);
                    setAudioHealthError(audioHealthResult.reason?.message || 'Audio provider unavailable');
                }
            } finally {
                setLoading(false);
            }
        };

        loadHomeData();
    }, []);

    useEffect(() => {
        setSettings((previous) => ({ ...previous, theme }));
    }, [theme]);

    const normalizedNovels = useMemo(() => novels.map(normalizeNovel), [novels]);
    const featuredNovel = useMemo(() => normalizedNovels.reduce((best, novel) => {
        if (!best) return novel;
        if (novel.chapterCount > best.chapterCount) return novel;
        if (novel.chapterCount === best.chapterCount && novel.views > best.views) return novel;
        return best;
    }, null), [normalizedNovels]);

    const totalChapters = normalizedNovels.reduce((sum, novel) => sum + novel.chapterCount, 0);
    const scraperJobs = Object.values(jobs);
    const activeScraperJobs = scraperJobs.filter((job) => job.status === 'pending' || job.status === 'running' || job.status === 'detecting').length;
    const trackedJobCount = scraperJobs.length + audioJobs.length;
    const providerSummary = audioHealth?.provider === 'qwen3' ? `Qwen3 local � ${settings.ttsSpeed}x` : audioHealth?.provider === 'kokoro' ? `${settings.voice} � ${settings.ttsSpeed}x` : 'Audio provider unavailable';

    const updateProfileField = (key, value) => {
        setProfile((previous) => saveHomeProfile({ ...previous, [key]: value }));
    };

    const updateSetting = (key, value) => {
        const nextSettings = { ...settings, [key]: value };
        setSettings(nextSettings);
        if (key === 'theme') setTheme(value);
        saveReaderSettings(nextSettings);
    };

    const staggerContainer = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.1 } } };
    const fadeInUp = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' } } };

    return (
        <>
            <div className="min-h-screen p-4 md:p-8 pt-20 md:pt-8 flex flex-col md:flex-row gap-6 md:gap-8 max-w-[1600px] mx-auto">
                <motion.div className="flex-1 flex flex-col gap-6 md:gap-8 min-w-0" variants={staggerContainer} initial="hidden" animate="show">
                    <motion.div variants={fadeInUp} className="pt-10 md:pt-20 pb-8 md:pb-16 px-4 md:px-8 relative">
                        <div className="absolute top-0 right-0 w-96 h-96 bg-white/10 dark:bg-violet-600/10 rounded-full blur-[100px] -translate-y-1/2 translate-x-1/3 transition-colors duration-700" />
                        <div className="relative z-10 max-w-2xl">
                            <span className="inline-block mb-4 px-4 py-1.5 rounded-full border border-stone-300/40 dark:border-violet-500/20 bg-white/30 dark:bg-violet-900/40 text-stone-700 dark:text-violet-200 text-xs font-bold tracking-[0.2em] uppercase backdrop-blur-md">Local-First Reading Studio</span>
                            <h1 className="font-display text-4xl md:text-6xl font-bold text-stone-900 dark:text-white mb-6 tracking-tight drop-shadow-sm dark:drop-shadow-lg">Novel Reader</h1>
                            <p className="text-stone-800 dark:text-violet-200/80 text-lg md:text-xl leading-relaxed mb-8 max-w-xl font-medium dark:font-normal drop-shadow-sm dark:drop-shadow-none">Scrape, collect, read, and listen to your favorite web novels locally with high-quality TTS.</p>
                            <div className="flex flex-wrap gap-4 mt-4">
                                <Link to="/library" className="px-8 py-3 rounded-full text-white font-medium flex items-center gap-3 bg-gradient-to-r from-violet-500/90 to-indigo-500/90 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-sm dark:shadow-glow-md transition-all"><Library size={18} />Browse Library</Link>
                                <Link to="/scraper" className="px-8 py-3 rounded-full font-medium flex items-center gap-3 border border-stone-400/30 dark:border-violet-500/30 text-stone-700 dark:text-violet-200 hover:bg-white/50 dark:hover:bg-violet-500/10 hover:border-stone-400/60 dark:hover:border-violet-400/50 bg-white/30 dark:bg-transparent transition-all backdrop-blur-md"><Sparkles size={18} />Scrape New Novel</Link>
                            </div>
                        </div>
                    </motion.div>

                    <motion.div variants={fadeInUp} className="flex flex-col md:flex-row gap-6 mt-4">
                        {[{ to: '/scraper', title: 'Fast Scraping', copy: 'Automatically fetch new novels and keep your library updated locally.', icon: Sparkles }, { to: '/library', title: 'Organized Library', copy: 'Keep your novels, chapter counts, and playback settings easy to revisit.', icon: Library }, { to: '/library', title: 'Premium Reading', copy: 'Tune reader settings once and reuse them across chapters, audio, and theme changes.', icon: Headphones }].map(({ to, title, copy, icon: Icon }) => (
                            <Link key={title} to={to} className="glass-thin rounded-[32px] p-8 flex flex-col items-center text-center gap-4 group flex-1 hover:bg-white/30 dark:hover:bg-white/5 hover:-translate-y-2 transition-all duration-300 border border-white/50 dark:border-white/8">
                                <div className="w-14 h-14 rounded-full bg-stone-100/40 dark:bg-violet-500/10 border border-stone-300/40 dark:border-violet-500/20 text-stone-700 dark:text-violet-300 flex items-center justify-center group-hover:scale-110 group-hover:bg-white/70 dark:group-hover:bg-violet-500/20 group-hover:text-stone-800 dark:group-hover:text-violet-200 transition-all duration-300 shadow-sm dark:shadow-glow-sm"><Icon size={24} /></div>
                                <div className="flex-1"><h3 className="text-lg font-bold text-stone-800 dark:text-white mb-2">{title}</h3><p className="text-sm text-stone-700 dark:text-violet-200/60 leading-relaxed font-medium">{copy}</p></div>
                                <div className="mt-4 w-8 h-8 rounded-full border border-stone-300/40 dark:border-violet-500/20 bg-white/40 dark:bg-violet-900/30 flex items-center justify-center text-stone-600 dark:text-violet-400 group-hover:border-stone-400/60 dark:group-hover:border-violet-400/50 group-hover:text-stone-800 dark:group-hover:text-violet-200 transition-colors"><ArrowRight size={14} className="transform rotate-90" /></div>
                            </Link>
                        ))}
                    </motion.div>
                </motion.div>

                <motion.div className="w-full md:w-[320px] lg:w-[350px] flex-shrink-0 flex flex-col" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}>
                    <div className="flex justify-end mb-4 pr-1">
                        <button type="button" onClick={() => setShowProfilePanel(true)} className="w-12 h-12 rounded-full bg-white dark:bg-violet-900 border border-stone-300/50 dark:border-violet-500/40 overflow-hidden shadow-md dark:shadow-glow-md hover:scale-105 transition-transform group" title="Profile and Settings">
                            <img src={getAvatarUrl(profile)} alt={`${profile.displayName} avatar`} className="w-full h-full object-cover" />
                        </button>
                    </div>

                    <div className="mb-6 pl-4">
                        <h2 className="text-[26px] font-bold text-stone-800 dark:text-white tracking-wide truncate">
                            Hi, {profile.displayName}
                        </h2>
                    </div>

                    <div className="glass rounded-[32px] p-5 flex flex-col gap-4 mb-6 shadow-lg dark:shadow-glass-lg">
                        <div className="flex items-center justify-between gap-3 pl-1">
                            <h3 className="text-[11px] font-medium tracking-wide text-stone-600 dark:text-white/90 uppercase">Featured Novel</h3>
                            {featuredNovel && <span className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-white/50 dark:bg-violet-500/10 text-stone-600 dark:text-violet-200 border border-white/60 dark:border-violet-500/20">{formatNumber(featuredNovel.chapterCount)} chapters</span>}
                        </div>
                        {loading ? (
                            <div className="rounded-2xl glass-thin border border-white/60 dark:border-white/5 p-6 text-sm text-stone-600 dark:text-violet-200/70">Loading your local library...</div>
                        ) : featuredNovel ? (
                            <>
                                <Link to={`/novel/${featuredNovel.slug}`} className="relative rounded-2xl overflow-hidden glass-thin border border-white/60 dark:border-white/5 hover:border-stone-300/50 dark:hover:border-violet-500/40 group block transition-all duration-300">
                                    <div className="h-[160px] w-full bg-stone-100/40 dark:bg-abyss-300 relative">
                                        {featuredNovel.coverUrl ? <img src={featuredNovel.coverUrl} alt={featuredNovel.title} className="w-full h-full object-cover opacity-85 group-hover:opacity-100 transition-opacity duration-500" /> : <div className="w-full h-full bg-white/30 dark:bg-violet-900/40 flex items-center justify-center border border-stone-300/20 dark:border-transparent"><BookOpen size={32} className="text-stone-400 dark:text-violet-500/40" /></div>}
                                        <div className="absolute inset-0 bg-gradient-to-t from-white/85 dark:from-[#050308] via-transparent to-transparent opacity-95 backdrop-blur-[1px] dark:backdrop-blur-none" />
                                        <div className="absolute inset-0 bg-gradient-to-r from-stone-50/70 dark:from-[#050308]/65 to-transparent" />
                                        <div className="absolute bottom-4 left-4 right-4">
                                            <h4 className="font-bold text-stone-800 dark:text-white text-[15px] mb-2 leading-tight tracking-wide drop-shadow-sm dark:drop-shadow-md">{featuredNovel.title}</h4>
                                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-stone-700 dark:text-violet-200/80 font-medium">
                                                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 bg-white/55 dark:bg-black/25 border border-white/60 dark:border-white/10"><BookOpen size={10} /> {formatNumber(featuredNovel.chapterCount)} chapters</span>
                                                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 bg-white/55 dark:bg-black/25 border border-white/60 dark:border-white/10">{formatNumber(featuredNovel.views)} views</span>
                                            </div>
                                        </div>
                                    </div>
                                </Link>
                                <Link to={`/novel/${featuredNovel.slug}`} className="w-full rounded-full px-4 py-3 text-sm font-semibold text-center border border-stone-300/50 dark:border-violet-500/30 text-stone-700 dark:text-violet-100 hover:bg-white/60 dark:hover:bg-violet-500/15 transition-all flex items-center justify-center gap-2">Open Featured Novel<ArrowRight size={15} /></Link>
                            </>
                        ) : (
                            <div className="rounded-2xl glass-thin border border-white/60 dark:border-white/5 p-6 text-center flex flex-col gap-4">
                                <p className="text-sm text-stone-600 dark:text-violet-200/70">No novels in your local library yet.</p>
                                <Link to="/scraper" className="w-full rounded-full px-4 py-3 text-sm font-semibold text-center border border-stone-300/50 dark:border-violet-500/30 text-stone-700 dark:text-violet-100 hover:bg-white/60 dark:hover:bg-violet-500/15 transition-all flex items-center justify-center gap-2"><Sparkles size={15} />Scrape your first novel</Link>
                            </div>
                        )}
                    </div>

                    <button type="button" className="glass rounded-[32px] overflow-hidden relative border border-white/40 dark:border-white/5 min-h-[220px] flex flex-col justify-between shadow-lg dark:shadow-glass-lg group cursor-pointer hover:border-stone-400/40 dark:hover:border-violet-500/30 transition-all duration-300 text-left" onClick={togglePanel}>
                        {featuredNovel?.coverUrl && <div className="absolute inset-x-0 bottom-0 h-32 opacity-20 dark:opacity-30 z-0 pointer-events-none mix-blend-multiply dark:mix-blend-screen"><img src={featuredNovel.coverUrl} className="w-full h-full object-cover object-top blur-[2px] brightness-100 saturate-100 dark:brightness-125 dark:saturate-50 group-hover:blur-0 transition-all duration-700" alt="" /><div className="absolute inset-0 bg-gradient-to-t from-white/90 via-white/80 dark:from-[#050308] dark:via-[#050308]/80 to-transparent/10" /></div>}
                        <div className="relative z-10 p-5 flex flex-col h-full gap-4">
                            <div className="flex items-center justify-between gap-3"><h3 className="text-[13px] font-medium tracking-wide text-stone-700 dark:text-white/90 pl-1 uppercase">Downloads</h3><span className="text-[10px] uppercase tracking-[0.18em] text-stone-500 dark:text-violet-300/60 font-semibold">Real job data</span></div>
                            <div className="grid grid-cols-2 gap-3">
                                {[{ label: 'Active total', value: activeJobCount }, { label: 'Scraper', value: activeScraperJobs }, { label: 'Audio', value: activeAudioJobCount }, { label: 'Tracked', value: trackedJobCount }].map((metric) => (
                                    <div key={metric.label} className="bg-white/20 dark:bg-white/5 backdrop-blur-md rounded-2xl p-3 border border-white/50 dark:border-white/10 shadow-sm"><div className="text-lg font-bold text-stone-800 dark:text-white">{formatNumber(metric.value)}</div><div className="text-[10px] uppercase tracking-[0.14em] text-stone-500 dark:text-violet-300/60 font-semibold">{metric.label}</div></div>
                                ))}
                            </div>
                            <div className="mt-auto flex items-center justify-between gap-3 rounded-2xl bg-white/20 dark:bg-white/5 border border-white/50 dark:border-white/10 px-4 py-3 shadow-sm">
                                <div><p className="text-xs font-semibold text-stone-700 dark:text-violet-100">{trackedJobCount === 0 ? 'No jobs yet' : 'Open the downloads panel'}</p><p className="text-[11px] text-stone-500 dark:text-violet-200/65">{trackedJobCount === 0 ? 'Start a scrape or audio generation run to track progress here.' : 'Review active scraper and audio work in one place.'}</p></div>
                                <div className="flex items-center gap-1.5 text-stone-600 dark:text-violet-100 font-bold text-xs whitespace-nowrap"><Download size={14} className="text-stone-500 dark:text-violet-400 opacity-80" /> Open</div>
                            </div>
                        </div>
                    </button>
                </motion.div>
            </div>

            <HomeProfilePanel
                isOpen={showProfilePanel}
                onClose={() => setShowProfilePanel(false)}
                profile={profile}
                settings={settings}
                audioHealth={audioHealth}
                audioHealthError={audioHealthError}
                onProfileChange={updateProfileField}
                onSettingChange={updateSetting}
            />
        </>
    );
}

export default Home;
