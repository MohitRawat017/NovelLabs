import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { BookOpen, Filter, FolderUp, RefreshCw, Search } from 'lucide-react';
import { getNovels, importNovelFolder } from '../services/api';
import './Library.css';

function Library() {
    const [novels, setNovels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedGenre, setSelectedGenre] = useState('all');
    const [importing, setImporting] = useState(false);
    const [importMessage, setImportMessage] = useState('');
    const [importError, setImportError] = useState('');
    const importInputRef = useRef(null);

    const genres = ['all', 'Fantasy', 'Action', 'Adventure', 'Romance', 'Mystery', 'Xianxia', 'Martial Arts', 'Imported', 'Local'];

    useEffect(() => {
        fetchNovels();
    }, [searchQuery, selectedGenre]);

    useEffect(() => {
        if (importInputRef.current) {
            importInputRef.current.setAttribute('webkitdirectory', '');
            importInputRef.current.setAttribute('directory', '');
        }
    }, []);

    const fetchNovels = async () => {
        try {
            setLoading(true);
            const data = await getNovels({
                search: searchQuery || undefined,
                genre: selectedGenre !== 'all' ? selectedGenre : undefined,
            });
            setNovels(data.novels || []);
            setError(null);
        } catch (err) {
            setError(err.message);
            console.error('Failed to fetch novels:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleImportClick = () => {
        importInputRef.current?.click();
    };

    const handleFolderImport = async (event) => {
        const files = Array.from(event.target.files || []);
        if (files.length === 0) {
            return;
        }

        try {
            setImporting(true);
            setImportError('');
            setImportMessage('');
            const result = await importNovelFolder(files);
            setImportMessage(result?.message || 'Novel imported successfully');
            await fetchNovels();
        } catch (err) {
            setImportError(err.message || 'Failed to import novel folder');
        } finally {
            setImporting(false);
            event.target.value = '';
        }
    };

    const formatRelativeTime = (dateString) => {
        if (!dateString) return 'Unknown';
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
        if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
        return `${Math.floor(diffDays / 365)} years ago`;
    };

    const formatNumber = (value) => {
        return new Intl.NumberFormat().format(Number(value) || 0);
    };

    return (
        <div className="min-h-screen p-4 md:p-8 pt-20 md:pt-8 flex flex-col gap-6 md:gap-8 max-w-[1600px] mx-auto relative z-10">
            {/* Solid mask to hide global body background image from index.css */}
            <div className="fixed inset-0 z-[-2] bg-[#f5f5f4] dark:bg-[#050308] transition-colors duration-700 pointer-events-none" />
            {/* The transparent library artwork layer that overlays the solid mask */}
            <div className="library-bg-underlay library-base-bg" />
            
            <motion.div 
                className="flex-1 flex flex-col min-w-0"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5 }}
            >
                {/* 1. Header Area */}
                <header className="mb-6 px-2">
                    <h1 className="font-display text-4xl font-bold text-stone-900 dark:text-white mb-2 tracking-tight drop-shadow-sm dark:drop-shadow-lg">
                        Novel Library
                    </h1>
                    <p className="text-stone-700 dark:text-violet-200/80 text-lg font-medium dark:font-normal">
                        Browse your collection of scraped and locally imported novels
                    </p>
                    {(importMessage || importError) && (
                        <div className={`mt-4 px-4 py-3 rounded-2xl glass-thin border ${importError ? 'border-red-500/30 text-red-600 dark:text-red-400 bg-red-500/10' : 'border-green-500/30 text-green-700 dark:text-green-300 bg-green-500/10'} text-sm font-medium`}>
                            {importError || importMessage}
                        </div>
                    )}
                </header>

                {/* 2. Unified Toolbar (Search | Filters | Sort | Import | Refresh) */}
                <div className="glass rounded-2xl p-4 mb-8 flex flex-col md:flex-row gap-4 items-center justify-between shadow-sm dark:shadow-glass-lg border border-white/50 dark:border-white/10 z-10 relative">
                    
                    {/* Search & Filters (Left side) */}
                    <div className="flex flex-col md:flex-row gap-3 w-full md:w-auto flex-1">
                        <div className="relative flex-1 max-w-sm">
                            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-500 dark:text-violet-400/70" />
                            <input
                                type="text"
                                className="w-full bg-white/40 dark:bg-black/20 border border-stone-300/40 dark:border-white/10 rounded-full py-2 pl-10 pr-4 text-sm text-stone-800 dark:text-violet-100 placeholder:text-stone-500 dark:placeholder:text-violet-400/50 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-all font-medium"
                                placeholder="Search novels..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                        
                        <div className="flex items-center gap-2 overflow-x-auto pb-2 md:pb-0 scrollbar-hide flex-wrap">
                            <Filter size={16} className="text-stone-500 dark:text-violet-400/70 ml-1 flex-shrink-0" />
                            {genres.slice(0, 5).map((genre) => (
                                <button
                                    key={genre}
                                    className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border ${
                                        selectedGenre === genre 
                                        ? 'bg-violet-500 text-white border-violet-500 shadow-sm dark:shadow-glow-sm' 
                                        : 'bg-white/30 dark:bg-white/5 border-stone-300/40 dark:border-white/10 text-stone-600 dark:text-violet-300 hover:bg-white/60 dark:hover:bg-violet-500/20'
                                    }`}
                                    onClick={() => setSelectedGenre(genre)}
                                >
                                    {genre === 'all' ? 'All' : genre}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Actions (Right side) */}
                    <div className="flex items-center gap-3 w-full md:w-auto justify-end flex-shrink-0">
                        <input
                            ref={importInputRef}
                            type="file"
                            multiple
                            accept=".txt,text/plain"
                            className="hidden-folder-input"
                            onChange={handleFolderImport}
                        />
                        <button onClick={handleImportClick} disabled={importing} className="glass-thin px-4 py-2 rounded-full text-xs font-bold text-stone-700 dark:text-violet-100 border border-stone-300/50 dark:border-violet-500/30 hover:bg-white/60 dark:hover:bg-violet-500/30 transition-all flex items-center gap-2 shadow-sm">
                            <FolderUp size={14} className={importing ? 'spin text-violet-500' : 'text-stone-500 dark:text-violet-400'} />
                            {importing ? 'Importing...' : 'Import'}
                        </button>
                        <button onClick={fetchNovels} disabled={loading || importing} className="glass-thin px-4 py-2 rounded-full text-xs font-bold text-stone-700 dark:text-violet-100 border border-stone-300/50 dark:border-violet-500/30 hover:bg-white/60 dark:hover:bg-violet-500/30 transition-all flex items-center gap-2 shadow-sm">
                            <RefreshCw size={14} className={loading ? 'spin text-violet-500' : 'text-stone-500 dark:text-violet-400'} />
                            Refresh
                        </button>
                    </div>
                </div>

                {/* 3. Main Novel Grid */}
                {error && (
                    <div className="mb-6 p-4 rounded-2xl glass-thin border border-red-500/30 bg-red-500/5 text-center flex flex-col items-center gap-3">
                        <p className="text-red-700 dark:text-red-400 font-medium">{error}</p>
                        <button onClick={fetchNovels} className="px-4 py-2 rounded-full bg-red-500/20 text-red-700 dark:text-red-300 text-sm font-semibold hover:bg-red-500/30 transition-colors">Retry</button>
                    </div>
                )}

                {loading ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                        {[1, 2, 3, 4, 5].map((n) => (
                            <div key={n} className="glass border border-white/30 dark:border-white/5 rounded-2xl overflow-hidden pointer-events-none animate-pulse">
                                <div className="aspect-[3/4] bg-stone-200/50 dark:bg-white/5 w-full"></div>
                                <div className="p-4 flex flex-col gap-2">
                                    <div className="h-4 bg-stone-200/60 dark:bg-white/10 rounded w-3/4"></div>
                                    <div className="h-3 bg-stone-200/50 dark:bg-white/5 rounded w-1/2"></div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <>
                        {novels.length > 0 ? (
                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                                {novels.map((novel) => (
                                    <Link to={`/novel/${novel.slug}`} key={novel.id} className="glass-thin border border-white/50 dark:border-white/10 rounded-2xl overflow-hidden group hover:-translate-y-1 hover:border-stone-400/50 dark:hover:border-violet-500/40 hover:shadow-lg dark:hover:shadow-glow-sm transition-all duration-300 flex flex-col">
                                        
                                        <div className="relative aspect-[3/4] bg-stone-100/40 dark:bg-abyss-300 overflow-hidden w-full">
                                            {novel.cover_url ? (
                                                <img src={novel.cover_url} alt={novel.title} className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-transform duration-700 group-hover:scale-105" />
                                            ) : (
                                                <div className="absolute inset-0 flex items-center justify-center text-stone-400 dark:text-violet-500/30">
                                                    <BookOpen size={40} strokeWidth={1.5} />
                                                </div>
                                            )}
                                            
                                            {/* Top Badges */}
                                            <div className="absolute top-2 left-2 px-2 py-1 rounded-md bg-stone-900/60 dark:bg-black/60 backdrop-blur-sm border border-white/20 text-[10px] font-bold text-white tracking-widest uppercase">
                                                {formatRelativeTime(novel.last_updated)}
                                            </div>

                                            {/* Bottom Gradient overlay for text readability if we placed text over the image, skipping here as text is below */}
                                        </div>

                                        <div className="p-4 flex flex-col flex-1 bg-white/20 dark:bg-transparent">
                                            <h3 className="font-bold text-stone-800 dark:text-white text-sm leading-snug line-clamp-2 mb-2 group-hover:text-violet-600 dark:group-hover:text-violet-300 transition-colors">
                                                {novel.title}
                                            </h3>
                                            
                                            <div className="flex flex-wrap gap-1 mb-3">
                                                {(novel.genres || '').split(',').filter(Boolean).slice(0, 2).map((genre) => (
                                                    <span key={genre} className="px-1.5 py-0.5 rounded text-[10px] bg-white/50 dark:bg-white/10 text-stone-600 dark:text-violet-200/80 border border-stone-300/40 dark:border-white/5 font-medium">
                                                        {genre.trim()}
                                                    </span>
                                                ))}
                                            </div>

                                            <div className="mt-auto pt-2 border-t border-stone-300/30 dark:border-white/5 flex items-center justify-between text-xs text-stone-500 dark:text-violet-300/60 font-medium tracking-wide">
                                                <span>{novel.chapter_count} Ch.</span>
                                                <span className="flex items-center gap-1"><BookOpen size={10} className="opacity-70" /> {formatNumber(novel.views)}</span>
                                            </div>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        ) : (
                            <div className="glass rounded-3xl p-12 text-center flex flex-col items-center justify-center gap-4 min-h-[400px] border border-white/40 dark:border-white/5 shadow-sm">
                                <div className="w-20 h-20 rounded-full bg-white/40 dark:bg-violet-900/30 flex items-center justify-center border border-stone-300/30 dark:border-violet-500/20 text-stone-400 dark:text-violet-500/50 mb-2">
                                    <BookOpen size={32} />
                                </div>
                                <h3 className="text-xl font-bold text-stone-800 dark:text-white">No novels found</h3>
                                <p className="text-stone-600 dark:text-violet-200/70 max-w-sm mb-4 font-medium">
                                    Import a local folder or scrape a new novel from the web to start building your library.
                                </p>
                                <div className="flex flex-wrap items-center justify-center gap-3">
                                    <button onClick={handleImportClick} className="px-6 py-2.5 rounded-full text-white font-medium flex items-center gap-2 bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-sm transition-all text-sm">
                                        <FolderUp size={16} /> Import Folder
                                    </button>
                                    <Link to="/scraper" className="px-6 py-2.5 rounded-full font-medium flex items-center gap-2 border border-stone-400/40 dark:border-violet-500/30 text-stone-700 dark:text-violet-200 hover:bg-white/60 dark:hover:bg-violet-500/10 hover:border-stone-400 dark:hover:border-violet-400/50 transform bg-white/40 dark:bg-transparent transition-all backdrop-blur-sm text-sm">
                                        Scrape a Novel
                                    </Link>
                                </div>
                            </div>
                        )}

                        {/* Pagination Layout (Stub) */}
                        {novels.length > 0 && (
                            <div className="mt-12 flex justify-center pb-8">
                                <div className="glass-thin px-4 py-2 rounded-full border border-white/50 dark:border-white/10 flex items-center gap-2 shadow-sm">
                                    <button className="w-8 h-8 rounded-full flex items-center justify-center text-stone-500 dark:text-violet-400/50 hover:bg-white/50 dark:hover:bg-violet-500/20 hover:text-stone-800 dark:hover:text-white transition-colors" disabled>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                                    </button>
                                    <div className="px-3 text-xs font-bold text-stone-700 dark:text-violet-200 tracking-widest">
                                        PAGE 1
                                    </div>
                                    <button className="w-8 h-8 rounded-full flex items-center justify-center text-stone-500 dark:text-violet-400/80 hover:bg-white/50 dark:hover:bg-violet-500/20 hover:text-stone-800 dark:hover:text-white transition-colors">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                                    </button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </motion.div>
        </div>
    );
}

export default Library;