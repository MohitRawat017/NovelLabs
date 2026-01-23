import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ScrapingProvider } from './context/ScrapingContext';
import Navbar from './components/ui/Navbar';
import Home from './pages/Home';
import Library from './pages/Library';
import NovelDetail from './pages/NovelDetail';
import ChapterReader from './pages/ChapterReader';
import Scraper from './pages/Scraper';
import './index.css';

function App() {
  return (
    <Router>
      <ScrapingProvider>
        <div className="app">
          <Navbar />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/library" element={<Library />} />
              <Route path="/novel/:slug" element={<NovelDetail />} />
              <Route path="/novel/:slug/chapter/:chapterId" element={<ChapterReader />} />
              <Route path="/scraper" element={<Scraper />} />
            </Routes>
          </main>
        </div>
      </ScrapingProvider>
    </Router>
  );
}

export default App;

