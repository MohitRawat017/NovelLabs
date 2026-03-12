import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
    listAudioJobs,
    listScrapeJobs,
    getScrapeStatus,
    cancelScrapeJob,
    removeScrapeJob,
} from '../services/api';

const ScrapingContext = createContext();

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
        try {
            const serverJobs = await listScrapeJobs();
            setJobs(serverJobs);
        } catch (err) {
            console.error('Failed to fetch jobs:', err);
        }
    }, []);

    const refreshAudioJobs = useCallback(async (novelSlug) => {
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

    // Remove a job from tracking (and from server)
    const removeJob = useCallback(async (jobId) => {
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
        refreshScraperJobs();
        refreshAudioJobs();
    }, [refreshScraperJobs, refreshAudioJobs]);

    // Poll for updates on active jobs
    useEffect(() => {
        const activeJobs = Object.entries(jobs).filter(
            ([, job]) => job.status === 'pending' || job.status === 'running' || job.status === 'detecting'
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
        const activeAudioJobs = audioJobs.filter(
            (job) => job.status === 'queued' || job.status === 'pending' || job.status === 'generating'
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
        job => job.status === 'pending' || job.status === 'running' || job.status === 'detecting'
    ).length;
    const activeAudioJobCount = audioJobs.filter(
        (job) => job.status === 'queued' || job.status === 'pending' || job.status === 'generating'
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
            removeJob,
            refreshAudioJobs,
            togglePanel,
            closePanel
        }}>
            {children}
        </ScrapingContext.Provider>
    );
}
