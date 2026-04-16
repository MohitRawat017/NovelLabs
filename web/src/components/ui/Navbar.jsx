import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, Home, Library, Menu, MoonStar, Sparkles, SunMedium, X } from 'lucide-react';
import { useScrapingJobs } from '../../context/ScrapingContext';
import { useTheme } from '../../context/ThemeContext';
import { IS_READ_ONLY_MODE } from '../../config/runtime';
import ScrapingJobsPanel from './ScrapingJobsPanel';

const NAV_ITEMS = [
    { to: '/', label: 'Home', icon: Home },
    { to: '/library', label: 'Library', icon: Library },
    { to: '/scraper', label: 'Scrape', icon: Sparkles },
];

const BRAND_JAPANESE = 'ノベルリーダー';

function Navbar() {
    const location = useLocation();
    const { activeJobCount, togglePanel } = useScrapingJobs();
    const { theme, toggleTheme } = useTheme();
    const [mobileOpen, setMobileOpen] = useState(false);
    const navItems = IS_READ_ONLY_MODE
        ? NAV_ITEMS.filter((item) => item.to !== '/scraper')
        : NAV_ITEMS;

    const isActive = (path) => path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);
    const ThemeIcon = theme === 'light' ? MoonStar : SunMedium;

    return (
        <>
            <div className="hidden md:block fixed left-6 top-8 bottom-8 w-[104px] z-30">
                <div className="flex flex-col items-center mb-6">
                    <Link to="/" className="group relative text-center">
                        <span className="text-[15px] text-stone-700 dark:text-violet-100 font-semibold tracking-[0.18em] leading-none group-hover:text-stone-900 dark:group-hover:text-white transition-colors font-display whitespace-nowrap">{BRAND_JAPANESE}</span>
                    </Link>
                </div>

                <aside className="mx-auto flex flex-col items-center py-6 gap-3 glass rounded-[34px] h-[calc(100%-8rem)] w-[68px] shadow-lg dark:shadow-glass-lg border-white/40 dark:border-white/10">
                    <nav className="flex flex-col items-center gap-2 flex-1">
                        {navItems.map(({ to, label, icon: Icon }) => (
                            <motion.div key={to} whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.94 }}>
                                <Link to={to} title={label} className={`rail-icon ${isActive(to) ? 'active' : ''}`}>
                                    <Icon size={20} />
                                </Link>
                            </motion.div>
                        ))}
                    </nav>

                    <div className="flex flex-col items-center gap-1">
                        {!IS_READ_ONLY_MODE && (
                            <motion.button whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.94 }} onClick={togglePanel} title="Downloads" className="rail-icon relative">
                                <Download size={20} />
                                {activeJobCount > 0 && <span className="absolute top-1.5 right-1.5 min-w-[1rem] h-4 px-1 flex items-center justify-center bg-stone-700 dark:bg-violet-500 text-white text-[9px] font-bold rounded-full shadow-sm dark:shadow-glow-sm pointer-events-none">{activeJobCount}</span>}
                            </motion.button>
                        )}

                        <motion.button whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.94 }} onClick={toggleTheme} title={theme === 'light' ? 'Dark mode' : 'Light mode'} className="rail-icon">
                            <ThemeIcon size={20} />
                        </motion.button>
                    </div>
                </aside>
            </div>

            <header className="fixed top-3 left-3 right-3 z-30 md:hidden flex items-center justify-between px-4 py-3 glass rounded-2xl">
                <Link to="/" className="min-w-0">
                    <span className="text-[14px] font-semibold tracking-[0.12em] text-stone-700 dark:text-violet-100 truncate font-display">{BRAND_JAPANESE}</span>
                </Link>
                <div className="flex items-center gap-2">
                    {!IS_READ_ONLY_MODE && (
                        <motion.button whileTap={{ scale: 0.9 }} onClick={togglePanel} className="rail-icon relative h-9 w-9 rounded-full">
                            <Download size={17} />
                            {activeJobCount > 0 && <span className="absolute top-0.5 right-0.5 min-w-[14px] h-3.5 px-1 flex items-center justify-center bg-stone-700 dark:bg-violet-500 text-white text-[8px] font-bold rounded-full shadow-sm dark:shadow-glow-sm pointer-events-none">{activeJobCount}</span>}
                        </motion.button>
                    )}
                    <motion.button whileTap={{ scale: 0.9 }} onClick={toggleTheme} className="rail-icon h-9 w-9 rounded-full"><ThemeIcon size={17} /></motion.button>
                    <motion.button whileTap={{ scale: 0.9 }} onClick={() => setMobileOpen((value) => !value)} className="rail-icon h-9 w-9 rounded-full" aria-label="Toggle menu">{mobileOpen ? <X size={18} /> : <Menu size={18} />}</motion.button>
                </div>
            </header>

            <AnimatePresence>
                {mobileOpen && (
                    <>
                        <motion.div key="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="fixed inset-0 z-20 bg-black/40 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} />
                        <motion.div key="drawer" initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.22 }} className="fixed top-[calc(3.25rem+1rem)] left-3 right-3 z-30 glass rounded-2xl p-4 md:hidden">
                            <p className="text-[10px] text-stone-500 dark:text-violet-400/60 font-semibold tracking-[0.2em] uppercase mb-3">Navigation</p>
                            <nav className="flex flex-col gap-1">
                                {navItems.map(({ to, label, icon: Icon }) => (
                                    <Link key={to} to={to} onClick={() => setMobileOpen(false)} className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${isActive(to) ? 'bg-stone-200/50 dark:bg-violet-600/20 border border-stone-300/50 dark:border-violet-500/30 text-stone-800 dark:text-violet-200' : 'text-stone-500 dark:text-violet-300/70 hover:bg-stone-200/50 dark:hover:bg-violet-600/10 hover:text-stone-800 dark:hover:text-violet-200'}`}>
                                        <Icon size={18} />
                                        {label}
                                    </Link>
                                ))}
                            </nav>
                            {!IS_READ_ONLY_MODE && (
                                <>
                                    <div className="h-px bg-stone-200 dark:bg-violet-500/15 my-3" />
                                    <button onClick={() => { togglePanel(); setMobileOpen(false); }} className="flex items-center gap-3 px-3 py-2.5 rounded-xl w-full text-left text-sm font-medium text-stone-500 dark:text-violet-300/70 hover:bg-stone-200/50 dark:hover:bg-violet-600/10 hover:text-stone-800 dark:hover:text-violet-200 transition-all duration-200">
                                        <Download size={18} />
                                        Downloads
                                        {activeJobCount > 0 && <span className="ml-auto bg-stone-700 dark:bg-violet-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full shadow-sm dark:shadow-glow-sm">{activeJobCount}</span>}
                                    </button>
                                </>
                            )}
                        </motion.div>
                    </>
                )}
            </AnimatePresence>

            {!IS_READ_ONLY_MODE && <ScrapingJobsPanel />}
        </>
    );
}

export default Navbar;
