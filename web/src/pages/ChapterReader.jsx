import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Settings, Home, Loader, Headphones } from 'lucide-react';
import { getChapterContent, getAudioTimingsUrl } from '../services/api';
import SettingsModal, { getSettings } from '../components/ui/SettingsModal';
import AudioPlayer from '../components/ui/AudioPlayer';
import './ChapterReader.css';

function ChapterReader() {
    const { slug, chapterId } = useParams();
    const navigate = useNavigate();
    const [chapter, setChapter] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showSettings, setShowSettings] = useState(false);
    const [showAudio, setShowAudio] = useState(false);
    const [settings, setSettings] = useState(getSettings);

    // Karaoke highlighting state
    const [chunkTimings, setChunkTimings] = useState(null);
    const [activeChunkIndex, setActiveChunkIndex] = useState(-1);
    const chunkRefs = useRef([]);
    const contentRef = useRef(null);

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
            window.scrollTo(0, 0);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const fetchChunkTimings = async () => {
        try {
            console.log('Fetching timings for:', slug, chapterNum);
            const timingsUrl = getAudioTimingsUrl(slug, chapterNum);
            const res = await fetch(timingsUrl);
            if (res.ok) {
                const data = await res.json();
                console.log('Timings loaded:', data);
                setChunkTimings(data);
                // Initialize chunk refs array
                chunkRefs.current = new Array(data.chunks?.length || 0);
            } else {
                console.log('Timings not available, status:', res.status);
            }
        } catch (err) {
            console.log('Timings fetch error:', err);
        }
    };

    // Handle time updates from AudioPlayer with debouncing for smoother scrolling
    const handleTimeUpdate = useCallback((currentTime, playbackRate) => {
        if (!chunkTimings || !chunkTimings.chunks) return;

        const chunks = chunkTimings.chunks;
        let newActiveIndex = -1;

        // Find the currently active chunk based on time
        for (let i = 0; i < chunks.length; i++) {
            if (currentTime >= chunks[i].start && currentTime < chunks[i].end) {
                newActiveIndex = i;
                break;
            }
        }

        // Only update if the active chunk has changed
        if (newActiveIndex !== activeChunkIndex && newActiveIndex >= 0) {
            setActiveChunkIndex(newActiveIndex);

            // Auto-scroll to the active chunk with smooth behavior
            if (chunkRefs.current[newActiveIndex]) {
                const element = chunkRefs.current[newActiveIndex];
                const rect = element.getBoundingClientRect();
                const isVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;

                // Only scroll if the element is not fully visible
                if (!isVisible) {
                    element.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'nearest'
                    });
                }
            }
        }
    }, [chunkTimings, activeChunkIndex]);

    const goToChapter = (num) => {
        setActiveChunkIndex(-1);
        setChunkTimings(null);
        navigate(`/novel/${slug}/chapter/${num}`);
    };

    // Improved smart text segmenter - splits text into readable chunks
    const segmentText = (text, targetChars = 300, minChars = 150, maxChars = 450) => {
        const paragraphs = text.split(/\n+/).filter(p => p.trim());
        const chunks = [];

        for (const paragraph of paragraphs) {
            const trimmed = paragraph.trim();
            if (!trimmed) continue;

            // If paragraph is within limits, keep it as one chunk
            if (trimmed.length <= maxChars) {
                chunks.push({
                    text: trimmed,
                    type: 'paragraph'
                });
                continue;
            }

            // Split long paragraphs by sentences
            // Improved regex that handles periods, exclamations, questions, and ellipsis
            const sentenceRegex = /([^.!?]+[.!?]+(?:\s+|$))|([^.!?]+$)/g;
            const sentenceMatches = [...trimmed.matchAll(sentenceRegex)];
            const sentences = sentenceMatches.map(m => (m[1] || m[2] || '').trim()).filter(s => s);

            if (sentences.length === 0) {
                chunks.push({ text: trimmed, type: 'paragraph' });
                continue;
            }

            let currentChunk = '';

            for (let i = 0; i < sentences.length; i++) {
                const sentence = sentences[i];
                const nextSentence = sentences[i + 1];
                
                // Calculate what the chunk would be if we add this sentence
                const wouldBe = currentChunk ? currentChunk + ' ' + sentence : sentence;

                // Decision logic:
                // 1. If we have no chunk yet, start with this sentence
                if (!currentChunk) {
                    currentChunk = sentence;
                    continue;
                }

                // 2. If adding this sentence keeps us under maxChars, add it
                if (wouldBe.length <= maxChars) {
                    currentChunk = wouldBe;
                    
                    // If we're approaching target size and this is a good stopping point, cut here
                    if (currentChunk.length >= targetChars && (!nextSentence || currentChunk.length + nextSentence.length > maxChars)) {
                        chunks.push({ text: currentChunk, type: 'segment' });
                        currentChunk = '';
                    }
                    continue;
                }

                // 3. Adding would exceed maxChars
                if (currentChunk.length >= minChars) {
                    // Current chunk is good size, save it and start new chunk
                    chunks.push({ text: currentChunk, type: 'segment' });
                    currentChunk = sentence;
                } else {
                    // Current chunk is too small, but adding sentence would exceed max
                    // Choose based on which is closer to target
                    const currentDistance = Math.abs(targetChars - currentChunk.length);
                    const wouldBeDistance = Math.abs(targetChars - wouldBe.length);
                    
                    if (wouldBeDistance < currentDistance || wouldBe.length <= maxChars * 1.1) {
                        // Adding sentence gets us closer to target (with 10% tolerance)
                        currentChunk = wouldBe;
                    }
                    
                    chunks.push({ text: currentChunk, type: 'segment' });
                    currentChunk = wouldBe === currentChunk ? '' : sentence;
                }
            }

            // Don't forget the last chunk
            if (currentChunk) {
                chunks.push({ text: currentChunk, type: 'segment' });
            }
        }

        return chunks;
    };

    // Render chapter content with karaoke highlighting when audio is playing
    const renderChapterContent = () => {
        // If we have chunk timings and audio is active, show chunked content with karaoke highlighting
        if (chunkTimings && chunkTimings.chunks && showAudio) {
            console.log('Rendering with audio chunks, active index:', activeChunkIndex);
            return (
                <>
                    {chunkTimings.chunks.map((chunk, idx) => (
                        <p
                            key={idx}
                            ref={el => chunkRefs.current[idx] = el}
                            className={`chunk ${idx === activeChunkIndex ? 'chunk-active' : ''}`}
                        >
                            {chunk.text}
                        </p>
                    ))}
                </>
            );
        }

        // Default: show smartly segmented paragraphs for better readability
        const segments = segmentText(chapter.content);
        return segments.map((segment, idx) => {
            const isNewParagraph = segment.type === 'paragraph';
            const prevSegment = idx > 0 ? segments[idx - 1] : null;
            const shouldAddBreak = prevSegment && prevSegment.type === 'segment' && isNewParagraph;
            
            return (
                <p 
                    key={idx} 
                    className={`chunk ${isNewParagraph ? 'chunk-paragraph' : 'chunk-segment'}`}
                    style={shouldAddBreak ? { marginTop: '1.5em' } : undefined}
                >
                    {segment.text}
                </p>
            );
        });
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

                <button 
                    className="btn btn-ghost" 
                    onClick={() => setShowAudio(!showAudio)}
                >
                    <Headphones size={18} />
                    {showAudio ? 'Close' : 'Listen'}
                </button>

                <button className="btn btn-ghost" onClick={() => setShowSettings(true)}>
                    <Settings size={18} />
                    Settings
                </button>
            </header>

            <main className="reader-content" ref={contentRef}>
                <h1 className="chapter-title">{chapter.title}</h1>
                <article
                    className="chapter-text"
                    style={{
                        fontSize: `${settings.fontSize}px`,
                        fontFamily: settings.fontFamily
                    }}
                >
                    {renderChapterContent()}
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

            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSettingsChange={setSettings}
            />

            {showAudio && (
                <AudioPlayer
                    novelSlug={slug}
                    chapterNumber={chapterNum}
                    chapterTitle={chapter?.title}
                    settings={settings}
                    onClose={() => {
                        setShowAudio(false);
                        setActiveChunkIndex(-1);
                        setChunkTimings(null);
                    }}
                    onTimeUpdate={handleTimeUpdate}
                    onAudioReady={fetchChunkTimings}
                />
            )}
        </div>
    );
}

export default ChapterReader;