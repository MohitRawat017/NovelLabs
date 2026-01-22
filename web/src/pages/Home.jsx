import { Link } from 'react-router-dom';
import { Library, Sparkles, BookOpen } from 'lucide-react';
import './Home.css';

function Home() {
    return (
        <div className="home">
            <section className="hero">
                <div className="hero-content">
                    <h1 className="hero-title">
                        <span className="gradient-text">Novel Reader</span>
                    </h1>
                    <p className="hero-subtitle">
                        Scrape, read, and listen to your favorite web novels with high-quality TTS
                    </p>

                    <div className="hero-actions">
                        <Link to="/library" className="btn btn-primary">
                            <Library size={20} />
                            Browse Library
                        </Link>
                        <Link to="/scraper" className="btn btn-outline">
                            <Sparkles size={20} />
                            Scrape New Novel
                        </Link>
                    </div>
                </div>

                <div className="hero-visual">
                    <div className="floating-book">
                        <BookOpen size={120} />
                    </div>
                </div>
            </section>

            <section className="features">
                <div className="feature-card">
                    <div className="feature-icon">
                        <Sparkles />
                    </div>
                    <h3>Fast Scraping</h3>
                    <p>Automatically extract novels from various sources with CloudFlare bypass</p>
                </div>

                <div className="feature-card">
                    <div className="feature-icon">
                        <Library />
                    </div>
                    <h3>Organized Library</h3>
                    <p>Browse, search, and filter your collection by genre and title</p>
                </div>

                <div className="feature-card">
                    <div className="feature-icon">
                        <BookOpen />
                    </div>
                    <h3>Premium Reading</h3>
                    <p>Customizable reader with multiple fonts, themes, and TTS voices</p>
                </div>
            </section>
        </div>
    );
}

export default Home;
