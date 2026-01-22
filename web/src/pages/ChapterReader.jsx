import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Settings, Home } from 'lucide-react';
import './ChapterReader.css';

// Mock chapter content
const mockContent = `
The morning sun cast long shadows across the cultivator's mountain retreat. This was where legends were born and where the weak became strong.

"You think you can achieve immortality?" The elder's voice echoed through the stone chamber. "Millions have tried. Millions have failed."

But I knew something they didn't. I had lived this life before. Every mistake, every wrong turn, every failed breakthrough – I remembered them all. This time would be different.

The path of cultivation is cruel. It demands sacrifice. It demands blood. Most of all, it demands an unwavering will. Those who hesitate are consumed. Those who fear are destroyed.

I took my first step onto the path, knowing full well the price I would pay.

Chapter End.
`;

function ChapterReader() {
    const { slug, chapterId } = useParams();

    const chapterNum = parseInt(chapterId);
    const prevChapter = chapterNum > 0 ? chapterNum - 1 : null;
    const nextChapter = chapterNum + 1;

    return (
        <div className="reader">
            <header className="reader-header">
                <Link to={`/novel/${slug}`} className="btn btn-ghost">
                    <Home size={18} />
                    Novel
                </Link>

                <div className="chapter-nav">
                    {prevChapter !== null && (
                        <Link to={`/novel/${slug}/chapter/${prevChapter}`} className="btn btn-ghost">
                            <ChevronLeft size={18} />
                            Prev
                        </Link>
                    )}
                    <span className="chapter-indicator">Chapter {chapterNum}</span>
                    <Link to={`/novel/${slug}/chapter/${nextChapter}`} className="btn btn-ghost">
                        Next
                        <ChevronRight size={18} />
                    </Link>
                </div>

                <button className="btn btn-ghost">
                    <Settings size={18} />
                    Settings
                </button>
            </header>

            <main className="reader-content">
                <h1 className="chapter-title">Chapter {chapterNum}</h1>
                <article className="chapter-text">
                    {mockContent.split('\n\n').map((paragraph, idx) => (
                        <p key={idx}>{paragraph}</p>
                    ))}
                </article>
            </main>

            <footer className="reader-footer">
                <div className="chapter-nav">
                    {prevChapter !== null && (
                        <Link to={`/novel/${slug}/chapter/${prevChapter}`} className="btn btn-outline">
                            <ChevronLeft size={18} />
                            Previous Chapter
                        </Link>
                    )}
                    <Link to={`/novel/${slug}/chapter/${nextChapter}`} className="btn btn-primary">
                        Next Chapter
                        <ChevronRight size={18} />
                    </Link>
                </div>
            </footer>
        </div>
    );
}

export default ChapterReader;
