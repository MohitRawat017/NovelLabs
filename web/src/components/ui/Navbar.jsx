import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Library, Search, Sparkles } from 'lucide-react';
import './Navbar.css';

function Navbar() {
  const location = useLocation();
  
  const isActive = (path) => location.pathname === path;
  
  return (
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
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
