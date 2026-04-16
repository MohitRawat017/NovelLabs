import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, Play, Loader, CheckCircle, XCircle, RefreshCw, Pause, StopCircle } from 'lucide-react';
import { startScraping, getScrapeStatus } from '../services/api';
import { useScrapingJobs } from '../context/ScrapingContext';
import './Scraper.css';

function Scraper() {
    const navigate = useNavigate();
    const { addJob, pauseJob, resumeJob, cancelJob } = useScrapingJobs();
    const [url, setUrl] = useState('');
    const [startChapter, setStartChapter] = useState(1);
    const [endChapter, setEndChapter] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [jobId, setJobId] = useState(null);
    const [progress, setProgress] = useState(null);
    const [error, setError] = useState(null);
    const pollIntervalRef = useRef(null);

    // Poll for progress updates
    useEffect(() => {
        if (jobId && !['completed', 'failed', 'cancelled'].includes(progress?.status)) {
            pollIntervalRef.current = setInterval(async () => {
                try {
                    const status = await getScrapeStatus(jobId);
                    setProgress(status);

                    if (['completed', 'failed', 'cancelled'].includes(status.status)) {
                        clearInterval(pollIntervalRef.current);
                        setIsLoading(false);
                    }
                } catch (err) {
                    console.error('Failed to get status:', err);
                }
            }, 2000);

            return () => clearInterval(pollIntervalRef.current);
        }
    }, [jobId, progress?.status]);

    const handlePauseResume = async () => {
        if (!jobId || !progress) {
            return;
        }

        try {
            if (progress.status === 'paused') {
                await resumeJob(jobId);
                setProgress((prev) => (prev ? { ...prev, status: 'running', error: null } : prev));
            } else {
                await pauseJob(jobId);
                setProgress((prev) => (prev ? { ...prev, status: 'paused', error: null } : prev));
            }
        } catch (err) {
            setError(err.message || 'Failed to update scraper job state');
        }
    };

    const handleCancel = async () => {
        if (!jobId || !progress) {
            return;
        }

        try {
            await cancelJob(jobId);
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
            setProgress((prev) => (prev ? { ...prev, status: 'cancelled', error: 'Cancelled by user' } : prev));
            setIsLoading(false);
        } catch (err) {
            setError(err.message || 'Failed to cancel scraper job');
        }
    };

    const handleScrape = async (e) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        setProgress(null);

        try {
            // Pass null for endChapter if empty to trigger auto-detection
            const endValue = endChapter === '' ? null : parseInt(endChapter);
            const result = await startScraping(url, startChapter, endValue);

            const initialProgress = {
                status: endValue === null ? 'detecting' : 'pending',
                current_chapter: 0,
                total_chapters: result.total_chapters || 0,
                novel_title: null
            };

            setJobId(result.job_id);
            setProgress(initialProgress);

            // Add to global job tracking
            addJob(result.job_id, initialProgress);
        } catch (err) {
            setError(err.message);
            setIsLoading(false);
        }
    };

    const handleReset = () => {
        setJobId(null);
        setProgress(null);
        setError(null);
        setIsLoading(false);
        setUrl('');
        setStartChapter(1);
        setEndChapter('');
    };

    const getProgressPercentage = () => {
        if (!progress) return 0;
        return Math.round((progress.current_chapter / progress.total_chapters) * 100);
    };

    return (
        <div className="min-h-screen p-4 md:p-8 pt-20 md:pt-8 flex flex-col gap-6 md:gap-8 max-w-[1600px] mx-auto relative z-10">
            {/* Solid mask to hide global body background image from index.css */}
            <div className="fixed inset-0 z-[-2] bg-[#f5f5f4] dark:bg-[#050308] transition-colors duration-700 pointer-events-none" />
            
            {/* The transparent artwork layer inherited from Library style */}
            <div className="scraper-bg-underlay scraper-base-bg" />

            <motion.div 
                className="flex-1 flex flex-col items-center justify-center min-w-0 pb-12"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
            >
                <div className="w-full max-w-xl flex flex-col items-center text-center mb-10">
                    <div className="w-20 h-20 mb-6 flex items-center justify-center bg-white/30 dark:bg-violet-900/40 border border-stone-300/40 dark:border-violet-500/20 rounded-3xl text-stone-600 dark:text-violet-400 shadow-lg dark:shadow-glow-md backdrop-blur-md transform -rotate-6">
                        <Sparkles size={36} className="transform rotate-6" />
                    </div>
                    <h1 className="font-display text-4xl md:text-5xl font-bold text-stone-900 dark:text-white mb-3 tracking-tight drop-shadow-sm dark:drop-shadow-lg">
                        Novel Scraper
                    </h1>
                    <p className="text-stone-700 dark:text-violet-200/80 text-lg font-medium dark:font-normal max-w-sm">
                        Extract chapters directly from supported sources into your local library.
                    </p>
                </div>

                <div className="w-full max-w-xl">
                    {!progress ? (
                        <form className="glass rounded-[32px] p-6 md:p-8 border border-white/50 dark:border-white/10 shadow-xl dark:shadow-glass-lg" onSubmit={handleScrape}>
                            
                            <div className="mb-6">
                                <label htmlFor="url" className="block text-sm font-bold tracking-wide text-stone-800 dark:text-violet-100 mb-2 pl-1">
                                    NOVEL TOC URL
                                </label>
                                <input
                                    id="url"
                                    type="url"
                                    className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-2xl py-3 px-4 text-stone-800 dark:text-violet-100 placeholder:text-stone-500 dark:placeholder:text-violet-400/50 focus:outline-none focus:ring-2 focus:ring-violet-500/40 transition-all font-medium"
                                    placeholder="https://freewebnovel.com/novel-name.html"
                                    value={url}
                                    onChange={(e) => setUrl(e.target.value)}
                                    required
                                />
                                <span className="block text-[11px] font-medium text-stone-500 dark:text-violet-300/60 mt-2 pl-1">
                                    Paste the link to the novel's Table of Contents page.
                                </span>
                            </div>

                            <div className="grid grid-cols-2 gap-4 mb-8">
                                <div>
                                    <label htmlFor="start" className="block text-sm font-bold tracking-wide text-stone-800 dark:text-violet-100 mb-2 pl-1">
                                        START CHAPTER
                                    </label>
                                    <input
                                        id="start"
                                        type="number"
                                        className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-2xl py-3 px-4 text-stone-800 dark:text-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-500/40 transition-all font-bold"
                                        min="1"
                                        value={startChapter}
                                        onChange={(e) => setStartChapter(parseInt(e.target.value) || 1)}
                                    />
                                </div>

                                <div>
                                    <label htmlFor="end" className="block text-sm font-bold tracking-wide text-stone-800 dark:text-violet-100 mb-2 pl-1 flex items-center justify-between">
                                        END CHAPTER
                                        <span className="text-[10px] uppercase font-bold text-stone-500 dark:text-violet-400/50">Optional</span>
                                    </label>
                                    <input
                                        id="end"
                                        type="number"
                                        className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-2xl py-3 px-4 text-stone-800 dark:text-violet-100 placeholder:text-stone-500 dark:placeholder:text-violet-400/50 focus:outline-none focus:ring-2 focus:ring-violet-500/40 transition-all font-bold"
                                        min={startChapter}
                                        value={endChapter}
                                        placeholder="Auto-detect"
                                        onChange={(e) => setEndChapter(e.target.value)}
                                    />
                                </div>
                            </div>

                            {error && (
                                <div className="mb-6 p-4 rounded-xl glass-thin border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400 text-sm font-medium flex items-center gap-3">
                                    <XCircle size={18} className="flex-shrink-0" />
                                    <span>{error}</span>
                                </div>
                            )}

                            <button
                                type="submit"
                                className="w-full py-4 rounded-full text-white font-bold text-lg flex items-center justify-center gap-3 bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-md dark:shadow-glow-md transition-all transform hover:-translate-y-0.5"
                                disabled={isLoading}
                            >
                                {isLoading ? (
                                    <>
                                        <Loader size={22} className="spin" />
                                        Initializing...
                                    </>
                                ) : (
                                    <>
                                        <Play size={22} fill="currentColor" />
                                        Launch Scraper
                                    </>
                                )}
                            </button>
                        </form>
                    ) : (
                        <div className="glass rounded-[32px] p-8 md:p-10 text-center border border-white/50 dark:border-white/10 shadow-xl dark:shadow-glass-lg flex flex-col items-center">
                            
                            <div className="w-24 h-24 rounded-full bg-white/40 dark:bg-black/20 border border-stone-300/40 dark:border-white/5 flex items-center justify-center mb-6 shadow-sm">
                                {progress.status === 'completed' ? (
                                    <CheckCircle size={40} className="text-emerald-600 dark:text-emerald-400" />
                                ) : progress.status === 'paused' ? (
                                    <Pause size={40} className="text-amber-600 dark:text-amber-400" />
                                ) : progress.status === 'failed' ? (
                                    <XCircle size={40} className="text-red-600 dark:text-red-400" />
                                ) : (
                                    <Loader size={40} className="spin text-violet-600 dark:text-violet-400" />
                                )}
                            </div>

                            <h2 className="text-2xl font-bold text-stone-800 dark:text-white mb-2">
                                {progress.status === 'completed' ? 'Scraping Complete' :
                                    progress.status === 'paused' ? 'Scraping Paused' :
                                        progress.status === 'cancelled' ? 'Scraping Cancelled' :
                                    progress.status === 'failed' ? 'Scraping Failed' :
                                        progress.status === 'running' ? 'Extracting Chapters...' :
                                            progress.status === 'detecting' ? 'Analyzing Table of Contents...' :
                                                'Connecting...'}
                            </h2>

                            {progress.novel_title && (
                                <p className="text-[15px] font-bold tracking-wide text-violet-600 dark:text-violet-300 mb-8 border border-violet-500/20 bg-violet-500/5 px-4 py-1.5 rounded-full inline-block">
                                    {progress.novel_title}
                                </p>
                            )}

                            {progress.status !== 'failed' && progress.status !== 'detecting' && (
                                <div className="w-full mb-8">
                                    <div className="flex justify-between text-xs font-bold text-stone-600 dark:text-violet-200/80 mb-2 px-1 uppercase tracking-wider">
                                        <span>Progress</span>
                                        <span>{getProgressPercentage()}%</span>
                                    </div>
                                    <div className="h-3 w-full bg-stone-200/50 dark:bg-black/40 rounded-full overflow-hidden border border-stone-300/30 dark:border-white/5">
                                        <div
                                            className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full transition-all duration-300 ease-out"
                                            style={{ width: `${getProgressPercentage()}%` }}
                                        />
                                    </div>
                                    <p className="text-sm font-medium text-stone-500 dark:text-violet-300/60 mt-3">
                                        {progress.status === 'completed' 
                                            ? `Successfully secured ${progress.total_chapters} chapters in library.` 
                                            : progress.status === 'paused'
                                                ? `Paused at chapter ${progress.current_chapter} of ${progress.total_chapters}`
                                                : progress.status === 'cancelled'
                                                    ? `Cancelled at chapter ${progress.current_chapter} of ${progress.total_chapters}`
                                            : `Fetching ${progress.current_chapter} of ${progress.total_chapters} chapters`}
                                    </p>
                                </div>
                            )}

                            {progress.error && (
                                <div className="w-full mb-8 p-4 rounded-xl glass-thin border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400 text-sm font-medium flex items-center gap-3 text-left">
                                    <XCircle size={18} className="flex-shrink-0" />
                                    <span>{progress.error}</span>
                                </div>
                            )}

                            {['detecting', 'pending', 'running', 'paused'].includes(progress.status) && (
                                <div className="flex flex-col sm:flex-row gap-3 w-full justify-center mt-2">
                                    <button
                                        type="button"
                                        className="py-3 px-6 rounded-full text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-sm transition-all flex items-center justify-center gap-2"
                                        onClick={handlePauseResume}
                                    >
                                        {progress.status === 'paused' ? <Play size={16} /> : <Pause size={16} />}
                                        {progress.status === 'paused' ? 'Resume' : 'Pause'}
                                    </button>
                                    <button
                                        type="button"
                                        className="py-3 px-6 rounded-full text-stone-700 dark:text-violet-100 font-bold text-sm bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-violet-500/20 border border-stone-300/50 dark:border-white/10 transition-all flex items-center justify-center gap-2 backdrop-blur-sm"
                                        onClick={handleCancel}
                                    >
                                        <StopCircle size={16} />
                                        Cancel
                                    </button>
                                </div>
                            )}

                            <div className="flex flex-col sm:flex-row gap-3 w-full justify-center mt-2">
                                {progress.status === 'completed' && (
                                    <button
                                        className="py-3 px-6 rounded-full text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-sm transition-all flex items-center justify-center gap-2"
                                        onClick={() => navigate('/library')}
                                    >
                                        Access in Library
                                    </button>
                                )}

                                <button
                                    className="py-3 px-6 rounded-full text-stone-700 dark:text-violet-100 font-bold text-sm bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-violet-500/20 border border-stone-300/50 dark:border-white/10 transition-all flex items-center justify-center gap-2 backdrop-blur-sm"
                                    onClick={handleReset}
                                >
                                    <RefreshCw size={16} />
                                    Scrape Another
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </motion.div>
        </div>
    );
}

export default Scraper;
