import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Settings, Home, Loader } from 'lucide-react';
import { getChapterContent } from '../services/api';
import './ChapterReader.css';

function ChapterReader() {
    const { slug, chapterId } = useParams();
    const navigate = useNavigate();
    const [chapter, setChapter] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const chapterNum = parseInt(chapterId);

    useEffect(() => {
        fetchChapter();
    }, [slug, chapterId]);

    const fetchChapter = async () => {
        try {
            setLoading(true);
            const data = await getChapterContent(slug, chapterNum);
            setChapter(data);
            setError(null);
            // Scroll to top when chapter changes
            window.scrollTo(0, 0);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const goToChapter = (num) => {
        navigate(`/novel/${slug}/chapter/${num}`);
    };

    if (loading) {
        return (
            <div className="reader">
                <div className="loading-state">
                    <Loader size={32} className="spin" />
                    <p>Loading chapter...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="reader">
                <div className="error-state">
                    <h2>Error loading chapter</h2>
                    <p>{error}</p>
                    <Link to={`/novel/${slug}`} className="btn btn-primary">Back to Novel</Link>
                </div>
            </div>
        );
    }

    if (!chapter) return null;

    return (
        <div className="reader">
            <header className="reader-header">
                <Link to={`/novel/${slug}`} className="btn btn-ghost">
                    <Home size={18} />
                    Novel
                </Link>

                <div className="chapter-nav">
                    {chapter.prev_chapter !== null && (
                        <button
                            onClick={() => goToChapter(chapter.prev_chapter)}
                            className="btn btn-ghost"
                        >
                            <ChevronLeft size={18} />
                            Prev
                        </button>
                    )}
                    <span className="chapter-indicator">Chapter {chapter.chapter_number}</span>
                    {chapter.next_chapter !== null && (
                        <button
                            onClick={() => goToChapter(chapter.next_chapter)}
                            className="btn btn-ghost"
                        >
                            Next
                            <ChevronRight size={18} />
                        </button>
                    )}
                </div>

                <button className="btn btn-ghost">
                    <Settings size={18} />
                    Settings
                </button>
            </header>

            <main className="reader-content">
                <h1 className="chapter-title">{chapter.title}</h1>
                <article className="chapter-text">
                    {chapter.content.split('\n\n').map((paragraph, idx) => (
                        paragraph.trim() && <p key={idx}>{paragraph}</p>
                    ))}
                </article>
            </main>

            <footer className="reader-footer">
                <div className="chapter-nav">
                    {chapter.prev_chapter !== null && (
                        <button
                            onClick={() => goToChapter(chapter.prev_chapter)}
                            className="btn btn-outline"
                        >
                            <ChevronLeft size={18} />
                            Previous Chapter
                        </button>
                    )}
                    {chapter.next_chapter !== null && (
                        <button
                            onClick={() => goToChapter(chapter.next_chapter)}
                            className="btn btn-primary"
                        >
                            Next Chapter
                            <ChevronRight size={18} />
                        </button>
                    )}
                </div>
            </footer>
        </div>
    );
}

export default ChapterReader;
