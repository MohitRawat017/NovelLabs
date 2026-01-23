import { useScrapingJobs } from '../../context/ScrapingContext';
import { X, Loader, CheckCircle, XCircle, Trash2, Download, StopCircle } from 'lucide-react';
import './ScrapingJobsPanel.css';

function ScrapingJobsPanel() {
    const { jobs, isOpen, closePanel, removeJob, cancelJob } = useScrapingJobs();

    if (!isOpen) return null;

    const jobEntries = Object.entries(jobs);

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed':
                return <CheckCircle size={18} className="status-icon success" />;
            case 'failed':
            case 'cancelled':
                return <XCircle size={18} className="status-icon error" />;
            case 'detecting':
            case 'pending':
            case 'running':
            default:
                return <Loader size={18} className="status-icon spin" />;
        }
    };

    const getProgressPercent = (job) => {
        if (!job.total_chapters || job.total_chapters === 0) return 0;
        return Math.round((job.current_chapter / job.total_chapters) * 100);
    };

    const isJobActive = (status) => {
        return status === 'pending' || status === 'running' || status === 'detecting';
    };

    return (
        <>
            <div className="panel-overlay" onClick={closePanel} />
            <div className="scraping-jobs-panel">
                <div className="panel-header">
                    <h3>Scraping Jobs</h3>
                    <button className="panel-close" onClick={closePanel}>
                        <X size={20} />
                    </button>
                </div>

                <div className="panel-content">
                    {jobEntries.length === 0 ? (
                        <div className="no-jobs">
                            <Download size={32} className="no-jobs-icon" />
                            <p>No scraping jobs</p>
                            <span className="text-muted">Start scraping from the Webscrapers page</span>
                        </div>
                    ) : (
                        <div className="jobs-list">
                            {jobEntries.map(([jobId, job]) => (
                                <div key={jobId} className={`job-item ${job.status}`}>
                                    <div className="job-header">
                                        {getStatusIcon(job.status)}
                                        <span className="job-title">
                                            {job.novel_title || 'Unknown Novel'}
                                        </span>
                                        {isJobActive(job.status) && (
                                            <button
                                                className="job-cancel"
                                                onClick={() => cancelJob(jobId)}
                                                title="Cancel"
                                            >
                                                <StopCircle size={14} />
                                            </button>
                                        )}
                                        {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
                                            <button
                                                className="job-remove"
                                                onClick={() => removeJob(jobId)}
                                                title="Remove"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        )}
                                    </div>

                                    {job.status !== 'failed' && (
                                        <>
                                            <div className="job-progress-bar">
                                                <div
                                                    className="job-progress-fill"
                                                    style={{ width: `${getProgressPercent(job)}%` }}
                                                />
                                            </div>
                                            <div className="job-stats">
                                                <span>
                                                    {job.status === 'detecting'
                                                        ? 'Detecting chapters...'
                                                        : job.status === 'completed'
                                                            ? `Completed ${job.total_chapters} chapters`
                                                            : `${job.current_chapter} / ${job.total_chapters}`
                                                    }
                                                </span>
                                                <span>{getProgressPercent(job)}%</span>
                                            </div>
                                        </>
                                    )}

                                    {job.error && (
                                        <p className="job-error">{job.error}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

export default ScrapingJobsPanel;
