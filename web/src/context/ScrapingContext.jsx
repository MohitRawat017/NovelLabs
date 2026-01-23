import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { listScrapeJobs, getScrapeStatus, cancelScrapeJob, removeScrapeJob } from '../services/api';

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
    const [isOpen, setIsOpen] = useState(false);
    const pollIntervalRef = useRef(null);

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
        const fetchJobs = async () => {
            try {
                const serverJobs = await listScrapeJobs();
                setJobs(serverJobs);
            } catch (err) {
                console.error('Failed to fetch jobs:', err);
            }
        };
        fetchJobs();
    }, []);

    // Poll for updates on active jobs
    useEffect(() => {
        const activeJobs = Object.entries(jobs).filter(
            ([, job]) => job.status === 'pending' || job.status === 'running' || job.status === 'detecting'
        );

        if (activeJobs.length === 0) {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
            return;
        }

        pollIntervalRef.current = setInterval(async () => {
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
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, [jobs]);

    // Count active jobs
    const activeJobCount = Object.values(jobs).filter(
        job => job.status === 'pending' || job.status === 'running' || job.status === 'detecting'
    ).length;

    return (
        <ScrapingContext.Provider value={{
            jobs,
            activeJobCount,
            isOpen,
            addJob,
            cancelJob,
            removeJob,
            togglePanel,
            closePanel
        }}>
            {children}
        </ScrapingContext.Provider>
    );
}
