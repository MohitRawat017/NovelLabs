import { useState } from 'react';
import { Sparkles, Play, Loader } from 'lucide-react';
import './Scraper.css';

function Scraper() {
    const [url, setUrl] = useState('');
    const [startChapter, setStartChapter] = useState(1);
    const [endChapter, setEndChapter] = useState(10);
    const [isLoading, setIsLoading] = useState(false);
    const [progress, setProgress] = useState(null);

    const handleScrape = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setProgress({ current: 0, total: endChapter - startChapter + 1 });

        // Will call FastAPI backend here
        console.log('Scraping:', { url, startChapter, endChapter });

        // Simulating progress for now
        setTimeout(() => {
            setIsLoading(false);
            setProgress(null);
        }, 2000);
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
                                onChange={(e) => setStartChapter(parseInt(e.target.value))}
                            />
                        </div>

                        <div className="form-group">
                            <label htmlFor="end">End Chapter</label>
                            <input
                                id="end"
                                type="number"
                                className="input"
                                min={startChapter}
                                value={endChapter}
                                onChange={(e) => setEndChapter(parseInt(e.target.value))}
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        className="btn btn-primary btn-large"
                        disabled={isLoading}
                    >
                        {isLoading ? (
                            <>
                                <Loader size={20} className="spin" />
                                Scraping...
                            </>
                        ) : (
                            <>
                                <Play size={20} />
                                Start Scraping
                            </>
                        )}
                    </button>
                </form>

                {progress && (
                    <div className="progress-section">
                        <div className="progress-bar">
                            <div
                                className="progress-fill"
                                style={{ width: `${(progress.current / progress.total) * 100}%` }}
                            />
                        </div>
                        <p className="progress-text">
                            Scraped {progress.current} of {progress.total} chapters
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default Scraper;
