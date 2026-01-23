import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Library, Search, Sparkles, Download } from 'lucide-react';
import { useScrapingJobs } from '../../context/ScrapingContext';
import ScrapingJobsPanel from './ScrapingJobsPanel';
import './Navbar.css';

function Navbar() {
  const location = useLocation();
  const { activeJobCount, togglePanel } = useScrapingJobs();

  const isActive = (path) => location.pathname === path;

  return (
    <>
      <nav className="navbar">
        <div className="navbar-container">
          <Link to="/" className="navbar-brand">
            <BookOpen className="brand-icon" />
            <span className="brand-text">Novel Reader</span>
          </Link>

          <div className="navbar-links">
            <Link
              to="/scraper"
              className={`nav-link ${isActive('/scraper') ? 'active' : ''}`}
            >
              <Sparkles size={18} />
              Webscrapers
            </Link>

            <Link
              to="/library"
              className={`nav-link ${isActive('/library') ? 'active' : ''}`}
            >
              <Library size={18} />
              Novels
            </Link>

            <button className="nav-link nav-button">
              <Search size={18} />
              Random Novel
            </button>

            <button
              className={`jobs-indicator ${activeJobCount > 0 ? 'has-active' : ''}`}
              onClick={togglePanel}
              title="Scraping Jobs"
            >
              <Download size={20} />
              {activeJobCount > 0 && (
                <span className="jobs-badge">{activeJobCount}</span>
              )}
            </button>
          </div>
        </div>
      </nav>
      <ScrapingJobsPanel />
    </>
  );
}

export default Navbar;

