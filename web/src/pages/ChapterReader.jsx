import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Settings, Home, Loader, Headphones, MoreHorizontal } from 'lucide-react';
import { getChapterContent, getAudioTimingsUrl } from '../services/api';
import SettingsModal from '../components/ui/SettingsModal';
import { getSettings } from '../utils/readerSettings';
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
    const [showReaderMenu, setShowReaderMenu] = useState(false);
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

    useEffect(() => {
        setShowReaderMenu(false);
    }, [slug, chapterId, showSettings, showAudio]);

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
            <div className="min-h-screen p-4 md:p-8 pt-20 flex items-center justify-center">
                <div className="flex flex-col items-center gap-4 text-stone-500 dark:text-stone-400">
                    <Loader size={40} className="spin text-violet-500" />
                    <p className="font-bold tracking-widest uppercase text-sm">Loading manuscript...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen p-4 md:p-8 pt-20 flex items-center justify-center">
                <div className="glass p-8 rounded-3xl max-w-md text-center border-red-500/30">
                    <h2 className="text-2xl font-bold text-red-500 mb-4">Read Error</h2>
                    <p className="text-stone-600 dark:text-stone-300 mb-6">{error}</p>
                    <Link to={`/novel/${slug}`} className="px-6 py-3 rounded-xl text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 shadow-md inline-block">
                        Back to Novel
                    </Link>
                </div>
            </div>
        );
    }

    if (!chapter) return null;

    const renderReaderActions = () => (
        <>
            <button
                className={`px-4 py-2 rounded-xl font-bold text-sm transition-all flex items-center gap-2 ${showAudio ? 'bg-violet-500/20 text-violet-700 dark:text-violet-300' : 'text-stone-600 dark:text-stone-300 hover:bg-stone-200/50 dark:hover:bg-white/5'}`}
                onClick={() => setShowAudio(!showAudio)}
            >
                <Headphones size={16} />
                {showAudio ? 'Close Player' : 'Listen'}
            </button>

            <button 
                className="px-4 py-2 rounded-xl font-bold text-sm text-stone-600 dark:text-stone-300 hover:bg-stone-200/50 dark:hover:bg-white/5 transition-all flex items-center gap-2" 
                onClick={() => setShowSettings(true)}
            >
                <Settings size={16} />
                Settings
            </button>
        </>
    );

    return (
        <div className={`reader ${showAudio ? 'audio-active' : ''}`}>
            {/* Solid mask to hide global body background image from index.css */}
            <div className="fixed inset-0 z-[-2] bg-[#f5f5f4] dark:bg-[#050308] transition-colors duration-700 pointer-events-none" />
            
            {/* The transparent artwork layer containing the Chapter Palace images */}
            <div className="chapter-bg-underlay chapter-base-bg" />

            {/* --- Top Floating Header --- */}
            <div className="sticky top-4 md:top-6 z-40 px-4 md:px-8 max-w-[1200px] mx-auto w-full mb-8 md:mb-12">
                <header className="glass rounded-[24px] p-4 md:p-5 flex items-center justify-between border border-stone-200/60 dark:border-white/10 shadow-lg backdrop-blur-xl">
                    <div className="flex items-center gap-4">
                        <Link 
                            to={`/novel/${slug}`} 
                            className="w-10 h-10 rounded-full flex items-center justify-center bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-violet-500/20 border border-stone-300/50 dark:border-white/10 text-stone-700 dark:text-stone-300 transition-all shadow-sm"
                        >
                            <Home size={18} />
                        </Link>
                        
                        <div className="hidden sm:flex items-center gap-1 bg-white/30 dark:bg-black/20 p-1 rounded-full border border-stone-300/30 dark:border-white/5">
                            <button
                                onClick={() => chapter.prev_chapter && goToChapter(chapter.prev_chapter)}
                                disabled={!chapter.prev_chapter}
                                className={`w-9 h-9 rounded-full flex items-center justify-center transition-all ${chapter.prev_chapter ? 'hover:bg-white/50 dark:hover:bg-white/10 text-stone-700 dark:text-stone-300 cursor-pointer' : 'text-stone-400 dark:text-stone-600 opacity-50 cursor-not-allowed'}`}
                            >
                                <ChevronLeft size={18} />
                            </button>
                            <span className="px-3 text-xs font-bold uppercase tracking-widest text-stone-800 dark:text-stone-200">
                                CH {chapter.chapter_number}
                            </span>
                            <button
                                onClick={() => chapter.next_chapter && goToChapter(chapter.next_chapter)}
                                disabled={!chapter.next_chapter}
                                className={`w-9 h-9 rounded-full flex items-center justify-center transition-all ${chapter.next_chapter ? 'hover:bg-white/50 dark:hover:bg-white/10 text-stone-700 dark:text-stone-300 cursor-pointer' : 'text-stone-400 dark:text-stone-600 opacity-50 cursor-not-allowed'}`}
                            >
                                <ChevronRight size={18} />
                            </button>
                        </div>
                    </div>

                    <div className="flex items-center">
                        <div className="hidden md:flex gap-1 bg-white/30 dark:bg-black/20 p-1 rounded-2xl border border-stone-300/30 dark:border-white/5">
                            {renderReaderActions()}
                        </div>

                        <div className="md:hidden relative z-50">
                            <button
                                className="w-10 h-10 rounded-full flex items-center justify-center bg-white/50 dark:bg-white/5 border border-stone-300/50 dark:border-white/10 text-stone-700 dark:text-stone-300"
                                onClick={() => setShowReaderMenu(!showReaderMenu)}
                            >
                                <MoreHorizontal size={18} />
                            </button>

                            {showReaderMenu && (
                                <div className="absolute top-[calc(100%+0.5rem)] right-0 min-w-[180px] p-2 flex flex-col gap-1 glass-thin bg-white/90 dark:bg-[#110e15]/90 border-stone-200/80 dark:border-white/10 rounded-2xl shadow-xl">
                                    {renderReaderActions()}
                                </div>
                            )}
                        </div>
                    </div>
                </header>
            </div>

            {/* --- Main Reading Surface --- */}
            <main className="flex-1 max-w-[900px] w-full mx-auto px-4 sm:px-8 pb-32" ref={contentRef}>
                <div className="glass-thin p-8 md:p-14 lg:p-20 rounded-[32px] md:rounded-[48px] border border-white/60 dark:border-white/10 shadow-2xl dark:shadow-none bg-white/70 dark:bg-black/30 backdrop-blur-md mb-12">
                    
                    <h1 className="font-display text-3xl md:text-4xl lg:text-5xl font-bold text-stone-900 dark:text-white mb-12 lg:mb-16 text-center tracking-tight leading-tight">
                        {chapter.title}
                    </h1>
                    
                    <article
                        className="chapter-text text-stone-800 dark:text-stone-300 transition-colors duration-300"
                        style={{
                            fontSize: `${settings.fontSize}px`,
                            fontFamily: settings.fontFamily
                        }}
                    >
                        {renderChapterContent()}
                    </article>
                    
                    {/* Chapter Completion Mark */}
                    <div className="flex justify-center items-center gap-4 mt-20 opacity-50">
                        <div className="h-px bg-current w-16"></div>
                        <div className="w-2 h-2 rounded-full bg-current rotate-45"></div>
                        <div className="h-px bg-current w-16"></div>
                    </div>
                </div>

                {/* --- Bottom Navigation Floating Footer --- */}
                <footer className="max-w-[600px] mx-auto mb-20">
                    <div className="glass rounded-[24px] p-2 flex justify-between items-center border border-stone-200/60 dark:border-white/10 shadow-lg">
                        <button
                            onClick={() => chapter.prev_chapter && goToChapter(chapter.prev_chapter)}
                            disabled={!chapter.prev_chapter}
                            className={`px-5 py-3 rounded-xl font-bold text-sm transition-all flex items-center gap-2 ${chapter.prev_chapter ? 'text-stone-700 dark:text-stone-300 hover:bg-white/50 dark:hover:bg-white/10 cursor-pointer' : 'text-stone-400 dark:text-stone-600 opacity-50 cursor-not-allowed'}`}
                        >
                            <ChevronLeft size={16} />
                            Previous
                        </button>
                        
                        <button
                            onClick={() => chapter.next_chapter && goToChapter(chapter.next_chapter)}
                            disabled={!chapter.next_chapter}
                            className={`px-6 py-3 rounded-xl font-bold text-sm transition-all flex items-center gap-2 ${chapter.next_chapter ? 'bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-indigo-600 dark:hover:from-violet-500 dark:hover:to-indigo-500 text-white shadow-md cursor-pointer' : 'text-stone-400 dark:text-stone-600 opacity-50 cursor-not-allowed border border-stone-200/50 dark:border-white/10'}`}
                        >
                            Next Chapter
                            <ChevronRight size={16} />
                        </button>
                    </div>
                </footer>
            </main>

            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSettingsChange={setSettings}
            />

            {showAudio && (
                <div className="fixed bottom-0 left-0 right-0 z-50 animate-in slide-in-from-bottom-8 duration-300">
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
                </div>
            )}
        </div>
    );
}

export default ChapterReader;
