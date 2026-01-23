import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Play, Loader, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import { startScraping, getScrapeStatus } from '../services/api';
import { useScrapingJobs } from '../context/ScrapingContext';
import './Scraper.css';

function Scraper() {
    const navigate = useNavigate();
    const { addJob } = useScrapingJobs();
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
        if (jobId && progress?.status !== 'completed' && progress?.status !== 'failed') {
            pollIntervalRef.current = setInterval(async () => {
                try {
                    const status = await getScrapeStatus(jobId);
                    setProgress(status);

                    if (status.status === 'completed' || status.status === 'failed') {
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
        setUrl('');
        setStartChapter(1);
        setEndChapter('');
    };

    const getProgressPercentage = () => {
        if (!progress) return 0;
        return Math.round((progress.current_chapter / progress.total_chapters) * 100);
    };

    return (
        <div className="scraper">
            <div className="scraper-container">
                <header className="scraper-header">
                    <div className="scraper-icon">
                        <Sparkles size={32} />
                    </div>
                    <h1>Web Scraper</h1>
                    <p className="text-muted">Scrape novels from supported sources</p>
                </header>

                {!progress ? (
                    <form className="scraper-form" onSubmit={handleScrape}>
                        <div className="form-group">
                            <label htmlFor="url">Novel TOC URL</label>
                            <input
                                id="url"
                                type="url"
                                className="input"
                                placeholder="https://novelhi.com/s/index/Novel-Name"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                required
                            />
                            <span className="form-hint">Enter the table of contents URL of the novel</span>
                        </div>

                        <div className="form-row">
                            <div className="form-group">
                                <label htmlFor="start">Start Chapter</label>
                                <input
                                    id="start"
                                    type="number"
                                    className="input"
                                    min="1"
                                    value={startChapter}
                                    onChange={(e) => setStartChapter(parseInt(e.target.value) || 1)}
                                />
                            </div>

                            <div className="form-group">
                                <label htmlFor="end">End Chapter <span className="optional-tag">(optional)</span></label>
                                <input
                                    id="end"
                                    type="number"
                                    className="input"
                                    min={startChapter}
                                    value={endChapter}
                                    placeholder="Auto-detect"
                                    onChange={(e) => setEndChapter(e.target.value)}
                                />
                                <span className="form-hint">Leave empty to auto-detect total chapters</span>
                            </div>
                        </div>

                        {error && (
                            <div className="error-box">
                                <XCircle size={18} />
                                <span>{error}</span>
                            </div>
                        )}

                        <button
                            type="submit"
                            className="btn btn-primary btn-large"
                            disabled={isLoading}
                        >
                            {isLoading ? (
                                <>
                                    <Loader size={20} className="spin" />
                                    Starting...
                                </>
                            ) : (
                                <>
                                    <Play size={20} />
                                    Start Scraping
                                </>
                            )}
                        </button>
                    </form>
                ) : (
                    <div className="progress-section">
                        <div className="progress-header">
                            {progress.status === 'completed' ? (
                                <CheckCircle size={48} className="success-icon" />
                            ) : progress.status === 'failed' ? (
                                <XCircle size={48} className="error-icon" />
                            ) : (
                                <Loader size={48} className="spin" />
                            )}

                            <h2>
                                {progress.status === 'completed' ? 'Scraping Complete!' :
                                    progress.status === 'failed' ? 'Scraping Failed' :
                                        progress.status === 'running' ? 'Scraping in Progress...' :
                                            progress.status === 'detecting' ? 'Detecting total chapters...' :
                                                'Starting...'}
                            </h2>

                            {progress.novel_title && (
                                <p className="novel-title">{progress.novel_title}</p>
                            )}
                        </div>

                        {progress.status !== 'failed' && (
                            <>
                                <div className="progress-bar">
                                    <div
                                        className="progress-fill"
                                        style={{ width: `${getProgressPercentage()}%` }}
                                    />
                                </div>

                                <p className="progress-text">
                                    {progress.status === 'completed' ? (
                                        `Successfully scraped ${progress.total_chapters} chapters`
                                    ) : (
                                        `Scraped ${progress.current_chapter} of ${progress.total_chapters} chapters (${getProgressPercentage()}%)`
                                    )}
                                </p>
                            </>
                        )}

                        {progress.error && (
                            <div className="error-box">
                                <XCircle size={18} />
                                <span>{progress.error}</span>
                            </div>
                        )}

                        <div className="progress-actions">
                            {progress.status === 'completed' && (
                                <button
                                    className="btn btn-primary"
                                    onClick={() => navigate('/library')}
                                >
                                    Go to Library
                                </button>
                            )}

                            <button
                                className="btn btn-outline"
                                onClick={handleReset}
                            >
                                <RefreshCw size={18} />
                                Scrape Another Novel
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default Scraper;
