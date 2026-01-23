import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { BookOpen, Play, RefreshCw, Search, Loader, CheckCircle } from 'lucide-react';
import { getNovel, getChapters, updateNovel } from '../services/api';
import { useScrapingJobs } from '../context/ScrapingContext';
import './NovelDetail.css';

function NovelDetail() {
    const { slug } = useParams();
    const { addJob } = useScrapingJobs();
    const [novel, setNovel] = useState(null);
    const [chapters, setChapters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [sortOrder, setSortOrder] = useState('asc');
    const [updating, setUpdating] = useState(false);
    const [updateMessage, setUpdateMessage] = useState(null);

    // Fetch novel and chapters
    useEffect(() => {
        fetchData();
    }, [slug]);

    useEffect(() => {
        if (novel) {
            fetchChapters();
        }
    }, [sortOrder, searchQuery]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const novelData = await getNovel(slug);
            setNovel(novelData);

            const chaptersData = await getChapters(slug, { sort: sortOrder });
            setChapters(chaptersData.chapters || []);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const fetchChapters = async () => {
        try {
            const chaptersData = await getChapters(slug, {
                sort: sortOrder,
                search: searchQuery || undefined
            });
            setChapters(chaptersData.chapters || []);
        } catch (err) {
            console.error('Failed to fetch chapters:', err);
        }
    };

    const handleUpdate = async () => {
        setUpdating(true);
        setUpdateMessage(null);

        try {
            const result = await updateNovel(slug);

            if (result.job_id) {
                // Add job to global tracking
                addJob(result.job_id, {
                    status: 'pending',
                    current_chapter: 0,
                    total_chapters: result.missing_chapters?.length || 0,
                    novel_title: novel?.title,
                    error: null
                });
                setUpdateMessage(`Scraping ${result.missing_chapters?.length || 0} missing chapters...`);
            } else {
                setUpdateMessage(result.message);
            }
        } catch (err) {
            setUpdateMessage(`Error: ${err.message}`);
        } finally {
            setUpdating(false);
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

    if (loading) {
        return (
            <div className="novel-detail">
                <div className="novel-container">
                    <div className="loading-state">
                        <div className="spinner"></div>
                        <p>Loading novel...</p>
                    </div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="novel-detail">
                <div className="novel-container">
                    <div className="error-state">
                        <h2>Error</h2>
                        <p>{error}</p>
                        <Link to="/library" className="btn btn-primary">Back to Library</Link>
                    </div>
                </div>
            </div>
        );
    }

    if (!novel) return null;

    const firstChapter = chapters.length > 0 ? Math.min(...chapters.map(c => c.chapter_number)) : 0;

    return (
        <div className="novel-detail">
            <div className="novel-container">
                {/* Novel Header */}
                <header className="novel-header">
                    <div className="novel-cover-wrapper">
                        <div className="novel-cover-large">
                            {novel.cover_url ? (
                                <img src={novel.cover_url} alt={novel.title} />
                            ) : (
                                <div className="cover-placeholder-large">
                                    <BookOpen size={80} />
                                </div>
                            )}
                        </div>
                        <span className="update-badge-large">{formatRelativeTime(novel.last_updated)}</span>
                    </div>

                    <div className="novel-meta">
                        <h1 className="novel-title-large">{novel.title}</h1>

                        <div className="novel-genres-large">
                            {(novel.genres || '').split(',').map(genre => (
                                <span key={genre} className="genre-tag">{genre.trim()}</span>
                            ))}
                        </div>

                        <p className="novel-views">Views: {(novel.views || 0).toLocaleString()}</p>

                        <p className="novel-description">
                            <strong>Description:</strong> {novel.description || 'No description available.'}
                        </p>

                        <div className="novel-actions">
                            <Link to={`/novel/${slug}/chapter/${firstChapter}`} className="btn btn-outline">
                                <Play size={18} />
                                Start Reading
                            </Link>
                            <button className="btn btn-outline">
                                <BookOpen size={18} />
                                Continue Reading
                            </button>
                            <button
                                className="btn btn-outline"
                                onClick={handleUpdate}
                                disabled={updating}
                            >
                                {updating ? (
                                    <>
                                        <Loader size={18} className="spin" />
                                        Checking...
                                    </>
                                ) : (
                                    <>
                                        <RefreshCw size={18} />
                                        Update Novel
                                    </>
                                )}
                            </button>
                        </div>

                        {updateMessage && (
                            <div className={`update-message ${updateMessage.includes('Error') ? 'error' : 'success'}`}>
                                {updateMessage.includes('Error') ? null : <CheckCircle size={16} />}
                                {updateMessage}
                            </div>
                        )}

                        <div className="sort-controls">
                            <span>Sort Chapters:</span>
                            <button
                                className={`sort-btn ${sortOrder === 'asc' ? 'active' : ''}`}
                                onClick={() => setSortOrder('asc')}
                            >
                                Ascending
                            </button>
                            <button
                                className={`sort-btn ${sortOrder === 'desc' ? 'active' : ''}`}
                                onClick={() => setSortOrder('desc')}
                            >
                                Descending
                            </button>
                        </div>
                    </div>
                </header>

                {/* Chapter Search */}
                <div className="chapter-search">
                    <input
                        type="text"
                        className="input"
                        placeholder="Search chapters..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>

                {/* Chapter Grid */}
                <div className="chapter-grid">
                    {chapters.map(chapter => (
                        <Link
                            key={chapter.id}
                            to={`/novel/${slug}/chapter/${chapter.chapter_number}`}
                            className="chapter-btn"
                        >
                            Chapter {chapter.chapter_number}
                        </Link>
                    ))}

                    {chapters.length === 0 && (
                        <div className="empty-chapters">
                            <p>No chapters found</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default NovelDetail;
