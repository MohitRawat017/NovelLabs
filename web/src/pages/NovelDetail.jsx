import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { BookOpen, Play, RefreshCw, Search, ArrowUp, ArrowDown } from 'lucide-react';
import './NovelDetail.css';

// Mock data - will be replaced with API calls
const mockNovel = {
    id: 1,
    slug: 'reverend-insanity',
    title: "A Regressor's Tale of Cultivation",
    cover: '/covers/reverend-insanity.jpg',
    genres: ['Action', 'Adventure', 'Fantasy', 'Mystery', 'Xianxia', 'Martial Arts', 'Romance', 'Tragedy'],
    views: 34090,
    description: 'On the way to a company workshop, we fell into a world of immortal cultivators while still in the car.',
    lastUpdated: '5 months ago',
    chapters: Array.from({ length: 100 }, (_, i) => ({
        id: i,
        number: i,
        title: `Chapter ${i}`
    }))
};

function NovelDetail() {
    const { slug } = useParams();
    const [searchQuery, setSearchQuery] = useState('');
    const [sortOrder, setSortOrder] = useState('asc');

    const novel = mockNovel; // Will fetch by slug later

    const filteredChapters = novel.chapters
        .filter(ch => ch.title.toLowerCase().includes(searchQuery.toLowerCase()))
        .sort((a, b) => sortOrder === 'asc' ? a.number - b.number : b.number - a.number);

    return (
        <div className="novel-detail">
            <div className="novel-container">
                {/* Novel Header */}
                <header className="novel-header">
                    <div className="novel-cover-wrapper">
                        <div className="novel-cover-large">
                            <div className="cover-placeholder-large">
                                <BookOpen size={80} />
                            </div>
                        </div>
                        <span className="update-badge-large">{novel.lastUpdated}</span>
                    </div>

                    <div className="novel-meta">
                        <h1 className="novel-title-large">{novel.title}</h1>

                        <div className="novel-genres-large">
                            {novel.genres.map(genre => (
                                <span key={genre} className="genre-tag">{genre}</span>
                            ))}
                        </div>

                        <p className="novel-views">Views: {novel.views.toLocaleString()}</p>

                        <p className="novel-description">
                            <strong>Description:</strong> {novel.description}
                        </p>

                        <div className="novel-actions">
                            <Link to={`/novel/${slug}/chapter/0`} className="btn btn-outline">
                                <Play size={18} />
                                Start Reading
                            </Link>
                            <button className="btn btn-outline">
                                <BookOpen size={18} />
                                Continue Reading
                            </button>
                            <button className="btn btn-outline">
                                <RefreshCw size={18} />
                                Update Novel
                            </button>
                        </div>

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
                    {filteredChapters.map(chapter => (
                        <Link
                            key={chapter.id}
                            to={`/novel/${slug}/chapter/${chapter.id}`}
                            className="chapter-btn"
                        >
                            Chapter {chapter.number}
                        </Link>
                    ))}
                </div>
            </div>
        </div>
    );
}

export default NovelDetail;
