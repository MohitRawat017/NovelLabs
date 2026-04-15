import { useScrapingJobs } from '../../context/ScrapingContext';
import { X, Loader, CheckCircle, XCircle, Trash2, Download, StopCircle, Headphones, Sparkles, Pause, Play } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './ScrapingJobsPanel.css';

function ScrapingJobsPanel() {
    const {
        jobs,
        audioJobs,
        isOpen,
        closePanel,
        removeJob,
        cancelJob,
        pauseJob,
        resumeJob,
        pauseAudioGeneration,
        resumeAudioGeneration,
        cancelAudioGeneration,
    } = useScrapingJobs();

    const scraperJobEntries = Object.entries(jobs);
    const hasAnyJobs = scraperJobEntries.length > 0 || audioJobs.length > 0;

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed':
                return <CheckCircle size={18} className="text-emerald-500" />;
            case 'paused':
                return <Pause size={18} className="text-amber-500" />;
            case 'failed':
            case 'cancelled':
                return <XCircle size={18} className="text-red-500" />;
            case 'detecting':
            case 'pending':
            case 'running':
            default:
                return <Loader size={18} className="text-violet-500 animate-spin" />;
        }
    };

    const getProgressPercent = (job, type) => {
        if (type === 'audio') {
            return Math.max(0, Math.min(100, Math.round(job.progress || 0)));
        }
        if (!job.total_chapters || job.total_chapters === 0) return 0;
        return Math.round((job.current_chapter / job.total_chapters) * 100);
    };

    const isScraperJobRunning = (status) => status === 'pending' || status === 'running' || status === 'detecting';
    const isScraperJobPaused = (status) => status === 'paused';
    const isAudioJobRunning = (status) => status === 'queued' || status === 'pending' || status === 'generating';
    const isAudioJobPaused = (status) => status === 'paused';
    const getAudioProviderBadgeClass = (provider) => {
        if (provider === 'qwen3') {
            return 'bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400';
        }
        if (provider === 'elevenlabs') {
            return 'bg-orange-100 text-orange-600 dark:bg-orange-500/10 dark:text-orange-400';
        }
        return 'bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400';
    };
    const getAudioProviderBorderClass = (provider) => {
        if (provider === 'qwen3') {
            return 'border-amber-500/30 dark:border-amber-400/20';
        }
        if (provider === 'elevenlabs') {
            return 'border-orange-500/30 dark:border-orange-400/20';
        }
        return 'border-blue-500/30 dark:border-blue-400/20';
    };
    const getAudioProgressClass = (provider, status) => {
        if (status === 'completed') {
            return 'bg-gradient-to-r from-emerald-400 to-emerald-500';
        }
        if (provider === 'qwen3') {
            return 'bg-gradient-to-r from-amber-400 to-amber-500';
        }
        if (provider === 'elevenlabs') {
            return 'bg-gradient-to-r from-orange-400 to-orange-500';
        }
        return 'bg-gradient-to-r from-blue-400 to-blue-500';
    };
    const getAudioProviderLabel = (provider) => {
        if (provider === 'qwen3') {
            return 'Qwen';
        }
        if (provider === 'elevenlabs') {
            return 'ElevenLabs';
        }
        return 'Kokoro';
    };

    const renderEmptySection = (copy) => (
        <div className="p-4 rounded-2xl border border-dashed border-stone-300 dark:border-white/10 text-stone-500 dark:text-stone-400 text-center text-sm font-medium">
            {copy}
        </div>
    );

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div
                        className="fixed inset-0 z-[109] bg-stone-900/10 dark:bg-black/40 backdrop-blur-sm"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={closePanel}
                    />

                    <motion.aside
                        className="fixed top-[4.5rem] md:top-5 left-3 right-3 md:left-auto md:right-5 z-[110] w-auto md:w-[24rem] max-h-[calc(100dvh-5.25rem)] md:max-h-[calc(100dvh-2.5rem)] flex flex-col overflow-hidden rounded-[1.65rem] glass shadow-2xl border border-white/40 dark:border-white/10"
                        initial={{ opacity: 0, y: -20, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ duration: 0.2, ease: 'easeOut' }}
                    >
                        <div className="flex items-center justify-between gap-4 p-4 md:p-[1.1rem] border-b border-stone-200/50 dark:border-white/10 bg-white/40 dark:bg-white/5">
                            <h3 className="flex items-center gap-2 m-0 text-sm font-bold tracking-widest uppercase text-stone-600 dark:text-stone-300">
                                <Download size={16} />
                                Downloads
                            </h3>
                            <button 
                                type="button" 
                                onClick={closePanel} 
                                className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 hover:bg-white/80 dark:hover:bg-white/10 transition-all"
                                aria-label="Close downloads panel"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="overflow-y-auto p-4 md:p-[1.1rem]">
                            {!hasAnyJobs ? (
                                <div className="flex flex-col items-center gap-4 py-12 px-4 text-center">
                                    <div className="flex items-center justify-center w-16 h-16 rounded-2xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-violet-500">
                                        <Download size={32} />
                                    </div>
                                    <p className="m-0 font-bold text-stone-800 dark:text-stone-200">No active jobs</p>
                                    <span className="text-sm text-stone-500 dark:text-stone-400">Scraper and audio generation appear here.</span>
                                </div>
                            ) : (
                                <div className="flex flex-col gap-6">
                                    <section className="flex flex-col gap-3">
                                        <div className="flex items-center justify-between">
                                            <span className="flex items-center gap-2 text-[0.75rem] font-bold tracking-[0.15em] uppercase text-stone-500 dark:text-stone-400">
                                                <Sparkles size={14} />
                                                Scraper Jobs
                                            </span>
                                        </div>

                                        {scraperJobEntries.length === 0 ? renderEmptySection('No scraper jobs yet.') : (
                                            <div className="flex flex-col gap-3">
                                                {scraperJobEntries.map(([jobId, job]) => (
                                                    <div key={jobId} className="flex flex-col gap-3 p-4 rounded-[1.15rem] border border-stone-200/50 dark:border-white/10 bg-white/40 dark:bg-white/5">
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="flex items-start gap-3 min-w-0">
                                                                <span className="flex items-center justify-center w-5 mt-0.5">{getStatusIcon(job.status)}</span>
                                                                <span className="block overflow-hidden text-ellipsis whitespace-nowrap font-bold text-stone-800 dark:text-stone-200">{job.novel_title || 'Unknown Novel'}</span>
                                                            </div>
                                                            <div className="flex gap-1.5">
                                                                {isScraperJobRunning(job.status) && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => pauseJob(jobId)}>
                                                                        <Pause size={16} />
                                                                    </button>
                                                                )}
                                                                {isScraperJobPaused(job.status) && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => resumeJob(jobId)}>
                                                                        <Play size={16} />
                                                                    </button>
                                                                )}
                                                                {(isScraperJobRunning(job.status) || isScraperJobPaused(job.status)) && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => cancelJob(jobId)}>
                                                                        <StopCircle size={16} />
                                                                    </button>
                                                                )}
                                                                {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => removeJob(jobId)}>
                                                                        <Trash2 size={16} />
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </div>

                                                        {job.status !== 'failed' && (
                                                            <>
                                                                <div className="h-1.5 overflow-hidden rounded-full bg-stone-200/80 dark:bg-white/10">
                                                                    <motion.div
                                                                        className={`h-full rounded-full ${job.status === 'completed' ? 'bg-gradient-to-r from-emerald-400 to-emerald-500' : 'bg-gradient-to-r from-violet-500 to-indigo-500'}`}
                                                                        initial={{ width: 0 }}
                                                                        animate={{ width: `${getProgressPercent(job, 'scraper')}%` }}
                                                                        transition={{ duration: 0.5 }}
                                                                    />
                                                                </div>
                                                                <div className="flex items-center justify-between text-xs font-bold tracking-wider uppercase text-stone-500 dark:text-stone-400">
                                                                    <span>
                                                                        {job.status === 'detecting'
                                                                            ? 'Detecting...'
                                                                            : job.status === 'paused'
                                                                                ? `Paused at ${job.current_chapter} / ${job.total_chapters} ch`
                                                                                : job.status === 'cancelled'
                                                                                    ? `Cancelled at ${job.current_chapter} / ${job.total_chapters} ch`
                                                                            : job.status === 'completed'
                                                                                ? `Done: ${job.total_chapters} ch`
                                                                                : `${job.current_chapter} / ${job.total_chapters} ch`}
                                                                    </span>
                                                                    <span>{getProgressPercent(job, 'scraper')}%</span>
                                                                </div>
                                                            </>
                                                        )}

                                                        {job.error && <p className="m-0 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400 text-xs">{job.error}</p>}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </section>

                                    <div className="h-px bg-gradient-to-r from-transparent via-stone-200 dark:via-white/10 to-transparent" />

                                    <section className="flex flex-col gap-3">
                                        <div className="flex items-center justify-between">
                                            <span className="flex items-center gap-2 text-[0.75rem] font-bold tracking-[0.15em] uppercase text-stone-500 dark:text-stone-400">
                                                <Headphones size={14} />
                                                Audio Jobs
                                            </span>
                                        </div>

                                        {audioJobs.length === 0 ? renderEmptySection('No audio jobs yet.') : (
                                            <div className="flex flex-col gap-3">
                                                {audioJobs.map((job) => (
                                                    <div key={job.job_id} className={`flex flex-col gap-3 p-4 rounded-[1.15rem] border ${getAudioProviderBorderClass(job.provider)} bg-white/40 dark:bg-white/5`}>
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="flex items-start gap-3 min-w-0">
                                                                <span className="flex items-center justify-center w-5 mt-0.5">{getStatusIcon(job.status)}</span>
                                                                <div className="flex flex-col gap-0.5 min-w-0">
                                                                    <span className="block overflow-hidden text-ellipsis whitespace-nowrap font-bold text-stone-800 dark:text-stone-200">{job.novel_title || job.novel_slug}</span>
                                                                    <span className="text-xs text-stone-500 dark:text-stone-400">Ch {job.chapter_number}: {job.chapter_title}</span>
                                                                </div>
                                                            </div>
                                                            {job.provider && (
                                                                <span className={`inline-flex items-center px-2 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase ${getAudioProviderBadgeClass(job.provider)}`}>
                                                                    {getAudioProviderLabel(job.provider)}
                                                                </span>
                                                            )}
                                                        </div>

                                                        {(isAudioJobRunning(job.status) || isAudioJobPaused(job.status)) && (
                                                            <div className="flex justify-end gap-1.5">
                                                                {isAudioJobRunning(job.status) && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => pauseAudioGeneration(job.novel_slug, job.chapter_number)}>
                                                                        <Pause size={16} />
                                                                    </button>
                                                                )}
                                                                {isAudioJobPaused(job.status) && (
                                                                    <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => resumeAudioGeneration(job.novel_slug, job.chapter_number)}>
                                                                        <Play size={16} />
                                                                    </button>
                                                                )}
                                                                <button type="button" className="flex items-center justify-center w-8 h-8 rounded-xl border border-stone-200/50 dark:border-white/10 bg-white/50 dark:bg-white/5 text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 transition-all" onClick={() => cancelAudioGeneration(job.novel_slug, job.chapter_number)}>
                                                                    <StopCircle size={16} />
                                                                </button>
                                                            </div>
                                                        )}

                                                        {job.status !== 'failed' && job.status !== 'cancelled' && (
                                                            <>
                                                                <div className="h-1.5 overflow-hidden rounded-full bg-stone-200/80 dark:bg-white/10">
                                                                    <motion.div
                                                                        className={`h-full rounded-full ${getAudioProgressClass(job.provider, job.status)}`}
                                                                        initial={{ width: 0 }}
                                                                        animate={{ width: `${getProgressPercent(job, 'audio')}%` }}
                                                                        transition={{ duration: 0.5 }}
                                                                    />
                                                                </div>
                                                                <div className="flex items-end justify-between gap-3 text-xs font-bold tracking-wider uppercase text-stone-500 dark:text-stone-400">
                                                                    <span className="flex flex-col gap-1">
                                                                        {job.total_chunks
                                                                            ? `${job.completed_chunks || 0} / ${job.total_chunks} chunks`
                                                                            : isAudioJobRunning(job.status)
                                                                                ? 'Preparing chunks...'
                                                                                : job.status}
                                                                        {job.estimated_remaining_seconds != null && isAudioJobRunning(job.status) && (
                                                                            <span className="text-[10px] text-stone-400 dark:text-stone-500">ETA: {Math.max(0, Math.round(job.estimated_remaining_seconds))}s</span>
                                                                        )}
                                                                    </span>
                                                                    <span>{getProgressPercent(job, 'audio')}%</span>
                                                                </div>
                                                            </>
                                                        )}

                                                        {job.error && <p className="m-0 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400 text-xs">{job.error}</p>}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </section>
                                </div>
                            )}
                        </div>
                    </motion.aside>
                </>
            )}
        </AnimatePresence>
    );
}

export default ScrapingJobsPanel;
