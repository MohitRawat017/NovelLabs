import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, BookOpen } from 'lucide-react';
import './Library.css';

// Mock data for now - will be replaced with API calls
const mockNovels = [
    {
        id: 1,
        slug: 'reverend-insanity',
        title: 'Reverend Insanity',
        cover: '/covers/reverend-insanity.jpg',
        genres: ['Fantasy', 'Action', 'Adventure', 'Martial Arts'],
        chapters: 2334,
        description: 'Humans are clever in tens of thousands of ways, Gu are the true refined essences of Heaven and Earth.',
        lastUpdated: '2 days ago'
    }
];

function Library() {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedGenre, setSelectedGenre] = useState('all');

    const genres = ['all', 'Fantasy', 'Action', 'Adventure', 'Romance', 'Mystery', 'Xianxia', 'Martial Arts'];

    const filteredNovels = mockNovels.filter(novel => {
        const matchesSearch = novel.title.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesGenre = selectedGenre === 'all' || novel.genres.includes(selectedGenre);
        return matchesSearch && matchesGenre;
    });

    return (
        <div className="library">
            <div className="library-container">
                <header className="library-header">
                    <h1>Novel Library</h1>
                    <p className="text-muted">Browse your collection of scraped novels</p>
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

                <div className="novels-grid">
                    {filteredNovels.map(novel => (
                        <Link to={`/novel/${novel.slug}`} key={novel.id} className="novel-card">
                            <div className="novel-cover">
                                <div className="cover-placeholder">
                                    <BookOpen size={48} />
                                </div>
                                <span className="update-badge">{novel.lastUpdated}</span>
                            </div>

                            <div className="novel-info">
                                <h3 className="novel-title">{novel.title}</h3>
                                <div className="novel-genres">
                                    {novel.genres.slice(0, 3).map(genre => (
                                        <span key={genre} className="badge">{genre}</span>
                                    ))}
                                </div>
                                <p className="novel-chapters">{novel.chapters} Chapters</p>
                            </div>
                        </Link>
                    ))}

                    {filteredNovels.length === 0 && (
                        <div className="empty-state">
                            <BookOpen size={64} />
                            <h3>No novels found</h3>
                            <p>Try adjusting your search or filters</p>
                            <Link to="/scraper" className="btn btn-primary">
                                Scrape a Novel
                            </Link>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Library;
