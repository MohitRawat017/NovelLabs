import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, BookOpen, RefreshCw } from 'lucide-react';
import { getNovels } from '../services/api';
import './Library.css';

function Library() {
    const [novels, setNovels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedGenre, setSelectedGenre] = useState('all');

    const genres = ['all', 'Fantasy', 'Action', 'Adventure', 'Romance', 'Mystery', 'Xianxia', 'Martial Arts'];

    // Fetch novels from API
    useEffect(() => {
        fetchNovels();
    }, [searchQuery, selectedGenre]);

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

    // Format relative time
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

    return (
        <div className="library">
            <div className="library-container">
                <header className="library-header">
                    <div className="header-content">
                        <div>
                            <h1>Novel Library</h1>
                            <p className="text-muted">Browse your collection of scraped novels</p>
                        </div>
                        <button onClick={fetchNovels} className="btn btn-outline" disabled={loading}>
                            <RefreshCw size={18} className={loading ? 'spin' : ''} />
                            Refresh
                        </button>
                    </div>
                </header>

                <div className="library-filters">
                    <div className="search-box">
                        <Search size={18} className="search-icon" />
                        <input
                            type="text"
                            className="input"
                            placeholder="Search novels..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>

                    <div className="genre-filters">
                        <Filter size={18} />
                        {genres.map(genre => (
                            <button
                                key={genre}
                                className={`genre-btn ${selectedGenre === genre ? 'active' : ''}`}
                                onClick={() => setSelectedGenre(genre)}
                            >
                                {genre === 'all' ? 'All' : genre}
                            </button>
                        ))}
                    </div>
                </div>

                {error && (
                    <div className="error-message">
                        <p>Error: {error}</p>
                        <button onClick={fetchNovels} className="btn btn-outline">Retry</button>
                    </div>
                )}

                {loading && (
                    <div className="loading-grid">
                        {[1, 2, 3, 4].map(n => (
                            <div key={n} className="novel-card skeleton-card">
                                <div className="novel-cover skeleton"></div>
                                <div className="novel-info">
                                    <div className="skeleton skeleton-title"></div>
                                    <div className="skeleton skeleton-text"></div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {!loading && (
                    <div className="novels-grid">
                        {novels.map(novel => (
                            <Link to={`/novel/${novel.slug}`} key={novel.id} className="novel-card">
                                <div className="novel-cover">
                                    {novel.cover_url ? (
                                        <img src={novel.cover_url} alt={novel.title} />
                                    ) : (
                                        <div className="cover-placeholder">
                                            <BookOpen size={48} />
                                        </div>
                                    )}
                                    <span className="update-badge">{formatRelativeTime(novel.last_updated)}</span>
                                </div>

                                <div className="novel-info">
                                    <h3 className="novel-title">{novel.title}</h3>
                                    <div className="novel-genres">
                                        {(novel.genres || '').split(',').slice(0, 3).map(genre => (
                                            <span key={genre} className="badge">{genre.trim()}</span>
                                        ))}
                                    </div>
                                    <p className="novel-chapters">{novel.chapter_count} Chapters</p>
                                </div>
                            </Link>
                        ))}

                        {novels.length === 0 && !error && (
                            <div className="empty-state">
                                <BookOpen size={64} />
                                <h3>No novels found</h3>
                                <p>Try adjusting your search or scrape a new novel</p>
                                <Link to="/scraper" className="btn btn-primary">
                                    Scrape a Novel
                                </Link>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

export default Library;
