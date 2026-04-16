import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
    listAudioJobs,
    listScrapeJobs,
    getScrapeStatus,
    cancelScrapeJob,
    pauseScrapeJob,
    resumeScrapeJob,
    removeScrapeJob,
    pauseAudioJob,
    resumeAudioJob,
    cancelAudioJob,
} from '../services/api';
import { IS_READ_ONLY_MODE } from '../config/runtime';

const ScrapingContext = createContext();
const SCRAPER_ACTIVE_STATUSES = new Set(['pending', 'running', 'detecting', 'paused']);
const AUDIO_ACTIVE_STATUSES = new Set(['queued', 'pending', 'generating', 'paused']);

export function useScrapingJobs() {
    const context = useContext(ScrapingContext);
    if (!context) {
        throw new Error('useScrapingJobs must be used within ScrapingProvider');
    }
    return context;
}

export function ScrapingProvider({ children }) {
    const [jobs, setJobs] = useState({});
    const [audioJobs, setAudioJobs] = useState([]);
    const [isOpen, setIsOpen] = useState(false);
    const scraperPollIntervalRef = useRef(null);
    const audioPollIntervalRef = useRef(null);

    const refreshScraperJobs = useCallback(async () => {
        if (IS_READ_ONLY_MODE) {
            setJobs({});
            return;
        }
        try {
            const serverJobs = await listScrapeJobs();
            setJobs(serverJobs);
        } catch (err) {
            console.error('Failed to fetch jobs:', err);
        }
    }, []);

    const refreshAudioJobs = useCallback(async (novelSlug) => {
        if (IS_READ_ONLY_MODE) {
            setAudioJobs([]);
            return;
        }
        try {
            const payload = await listAudioJobs(novelSlug);
            setAudioJobs(Array.isArray(payload?.jobs) ? payload.jobs : []);
        } catch (err) {
            console.error('Failed to fetch audio jobs:', err);
        }
    }, []);

    // Add a new job to track
    const addJob = useCallback((jobId, initialData) => {
        setJobs(prev => ({
            ...prev,
            [jobId]: initialData
        }));
    }, []);

    // Cancel a running job
    const cancelJob = useCallback(async (jobId) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await cancelScrapeJob(jobId);
            setJobs(prev => ({
                ...prev,
                [jobId]: { ...prev[jobId], status: 'cancelled', error: 'Cancelled by user' }
            }));
        } catch (err) {
            console.error('Failed to cancel job:', err);
        }
    }, []);

    const pauseJob = useCallback(async (jobId) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await pauseScrapeJob(jobId);
            setJobs(prev => ({
                ...prev,
                [jobId]: { ...prev[jobId], status: 'paused', error: null }
            }));
        } catch (err) {
            console.error('Failed to pause job:', err);
        }
    }, []);

    const resumeJob = useCallback(async (jobId) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await resumeScrapeJob(jobId);
            setJobs(prev => ({
                ...prev,
                [jobId]: { ...prev[jobId], status: 'running', error: null }
            }));
        } catch (err) {
            console.error('Failed to resume job:', err);
        }
    }, []);

    const pauseAudioGeneration = useCallback(async (novelSlug, chapterNumber) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await pauseAudioJob(novelSlug, chapterNumber);
            setAudioJobs(prev => prev.map(job => (
                job.novel_slug === novelSlug && job.chapter_number === chapterNumber
                    ? { ...job, status: 'paused', message: 'Paused by user' }
                    : job
            )));
        } catch (err) {
            console.error('Failed to pause audio job:', err);
        }
    }, []);

    const resumeAudioGeneration = useCallback(async (novelSlug, chapterNumber) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await resumeAudioJob(novelSlug, chapterNumber);
            setAudioJobs(prev => prev.map(job => (
                job.novel_slug === novelSlug && job.chapter_number === chapterNumber
                    ? { ...job, status: 'generating', message: 'Resuming generation' }
                    : job
            )));
        } catch (err) {
            console.error('Failed to resume audio job:', err);
        }
    }, []);

    const cancelAudioGeneration = useCallback(async (novelSlug, chapterNumber) => {
        if (IS_READ_ONLY_MODE) {
            return;
        }
        try {
            await cancelAudioJob(novelSlug, chapterNumber);
            setAudioJobs(prev => prev.map(job => (
                job.novel_slug === novelSlug && job.chapter_number === chapterNumber
                    ? { ...job, status: 'cancelled', message: 'Cancelled by user', error: 'Cancelled by user' }
                    : job
            )));
        } catch (err) {
            console.error('Failed to cancel audio job:', err);
        }
    }, []);

    // Remove a job from tracking (and from server)
    const removeJob = useCallback(async (jobId) => {
        if (IS_READ_ONLY_MODE) {
            setJobs(prev => {
                const newJobs = { ...prev };
                delete newJobs[jobId];
                return newJobs;
            });
            return;
        }
        try {
            await removeScrapeJob(jobId);
        } catch (err) {
            console.error('Failed to remove job from server:', err);
        }
        setJobs(prev => {
            const newJobs = { ...prev };
            delete newJobs[jobId];
            return newJobs;
        });
    }, []);

    // Toggle panel visibility
    const togglePanel = useCallback(() => {
        setIsOpen(prev => !prev);
    }, []);

    const closePanel = useCallback(() => {
        setIsOpen(false);
    }, []);

    // Fetch initial jobs on mount
    useEffect(() => {
        if (IS_READ_ONLY_MODE) {
            setJobs({});
            setAudioJobs([]);
            return;
        }
        refreshScraperJobs();
        refreshAudioJobs();
    }, [refreshScraperJobs, refreshAudioJobs]);

    // Poll for updates on active jobs
    useEffect(() => {
        if (IS_READ_ONLY_MODE) {
            if (scraperPollIntervalRef.current) {
                clearInterval(scraperPollIntervalRef.current);
                scraperPollIntervalRef.current = null;
            }
            return;
        }
        const activeJobs = Object.entries(jobs).filter(
            ([, job]) => SCRAPER_ACTIVE_STATUSES.has(job.status)
        );

        if (activeJobs.length === 0) {
            if (scraperPollIntervalRef.current) {
                clearInterval(scraperPollIntervalRef.current);
                scraperPollIntervalRef.current = null;
            }
            return;
        }

        scraperPollIntervalRef.current = setInterval(async () => {
            for (const [jobId] of activeJobs) {
                try {
                    const status = await getScrapeStatus(jobId);
                    setJobs(prev => ({
                        ...prev,
                        [jobId]: status
                    }));
                } catch (err) {
                    console.error(`Failed to get status for job ${jobId}:`, err);
                }
            }
        }, 3000);

        return () => {
            if (scraperPollIntervalRef.current) {
                clearInterval(scraperPollIntervalRef.current);
            }
        };
    }, [jobs]);

    useEffect(() => {
        if (IS_READ_ONLY_MODE) {
            if (audioPollIntervalRef.current) {
                clearInterval(audioPollIntervalRef.current);
                audioPollIntervalRef.current = null;
            }
            return;
        }
        const activeAudioJobs = audioJobs.filter(
            (job) => AUDIO_ACTIVE_STATUSES.has(job.status)
        );

        if (activeAudioJobs.length === 0) {
            if (audioPollIntervalRef.current) {
                clearInterval(audioPollIntervalRef.current);
                audioPollIntervalRef.current = null;
            }
            return;
        }

        audioPollIntervalRef.current = setInterval(() => {
            refreshAudioJobs();
        }, 3000);

        return () => {
            if (audioPollIntervalRef.current) {
                clearInterval(audioPollIntervalRef.current);
            }
        };
    }, [audioJobs, refreshAudioJobs]);

    // Count active jobs
    const activeScraperJobCount = Object.values(jobs).filter(
        job => SCRAPER_ACTIVE_STATUSES.has(job.status)
    ).length;
    const activeAudioJobCount = audioJobs.filter(
        (job) => AUDIO_ACTIVE_STATUSES.has(job.status)
    ).length;
    const activeJobCount = activeScraperJobCount + activeAudioJobCount;

    return (
        <ScrapingContext.Provider value={{
            jobs,
            audioJobs,
            activeJobCount,
            activeAudioJobCount,
            isOpen,
            addJob,
            cancelJob,
            pauseJob,
            resumeJob,
            removeJob,
            refreshAudioJobs,
            pauseAudioGeneration,
            resumeAudioGeneration,
            cancelAudioGeneration,
            togglePanel,
            closePanel
        }}>
            {children}
        </ScrapingContext.Provider>
    );
}
