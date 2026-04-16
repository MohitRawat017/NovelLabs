import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ScrapingProvider } from './context/ScrapingContext';
import { ThemeProvider } from './context/ThemeContext';
import Navbar from './components/ui/Navbar';
import Home from './pages/Home';
import Library from './pages/Library';
import NovelDetail from './pages/NovelDetail';
import ChapterReader from './pages/ChapterReader';
import Scraper from './pages/Scraper';
import { IS_READ_ONLY_MODE } from './config/runtime';
import './index.css';

function App() {
  return (
    <Router>
      <ThemeProvider>
        <ScrapingProvider>
          {/* Full-height flex shell: sidebar + main */}
          <div className="flex min-h-screen relative">
            <Navbar />
            {/* Main content shifts right on desktop to account for fixed floating sidebar */}
            <main className="flex-1 md:ml-[104px] min-h-screen overflow-y-auto relative z-10 p-6 md:pr-8">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/library" element={<Library />} />
                <Route path="/novel/:slug" element={<NovelDetail />} />
                <Route path="/novel/:slug/chapter/:chapterId" element={<ChapterReader />} />
                <Route path="/scraper" element={IS_READ_ONLY_MODE ? <Navigate to="/library" replace /> : <Scraper />} />
              </Routes>
            </main>
          </div>
        </ScrapingProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
