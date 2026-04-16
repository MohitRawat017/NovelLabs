import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { BookOpen, Play, RefreshCw, Loader, CheckCircle, Volume2, Sparkles } from 'lucide-react';
import {
    deleteNovelVoiceProfile,
    getAudioHealth,
    getChapters,
    getNovel,
    getNovelVoiceProfile,
    generateChapterAudio,
    updateNovel,
    uploadNovelVoiceProfile
} from '../services/api';
import { useScrapingJobs } from '../context/ScrapingContext';
import { IS_READ_ONLY_MODE } from '../config/runtime';
import { getSettings } from '../utils/readerSettings';
import './NovelDetail.css';

function NovelDetail() {
    const { slug } = useParams();
    const { addJob, refreshAudioJobs } = useScrapingJobs();
    const [novel, setNovel] = useState(null);
    const [chapters, setChapters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [sortOrder, setSortOrder] = useState('asc');
    const [updating, setUpdating] = useState(false);
    const [updateMessage, setUpdateMessage] = useState(null);
    const [sourceUrlInput, setSourceUrlInput] = useState('');
    const [audioHealth, setAudioHealth] = useState(null);
    const [voiceProfile, setVoiceProfile] = useState(null);
    const [voiceProfileLoading, setVoiceProfileLoading] = useState(true);
    const [voiceFile, setVoiceFile] = useState(null);
    const [voiceRefText, setVoiceRefText] = useState('');
    const [voiceDisplayName, setVoiceDisplayName] = useState('');
    const [voiceMessage, setVoiceMessage] = useState(null);
    const [voiceSaving, setVoiceSaving] = useState(false);
    const [audioGenerationMode, setAudioGenerationMode] = useState('range');
    const [selectedChapters, setSelectedChapters] = useState([]);
    const [rangeStart, setRangeStart] = useState('');
    const [rangeEnd, setRangeEnd] = useState('');
    const [audioBatchSubmitting, setAudioBatchSubmitting] = useState(false);
    const [audioBatchMessage, setAudioBatchMessage] = useState(null);

    // Fetch novel and chapters
    useEffect(() => {
        fetchData();
    }, [slug]);

    useEffect(() => {
        if (novel) {
            fetchChapters();
        }
    }, [sortOrder, searchQuery]);

    useEffect(() => {
        fetchVoiceProfile();
    }, [slug]);

    useEffect(() => {
        setSelectedChapters((previous) =>
            previous.filter((chapterNumber) =>
                chapters.some((chapter) => chapter.chapter_number === chapterNumber)
            )
        );
    }, [chapters]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const novelData = await getNovel(slug);
            setNovel(novelData);
            setSourceUrlInput(novelData?.source_toc_url || '');

            const chaptersData = await getChapters(slug, { sort: sortOrder });
            setChapters(chaptersData.chapters || []);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const fetchChapters = async () => {
        try {
            const chaptersData = await getChapters(slug, {
                sort: sortOrder,
                search: searchQuery || undefined
            });
            setChapters(chaptersData.chapters || []);
        } catch (err) {
            console.error('Failed to fetch chapters:', err);
        }
    };

    const fetchVoiceProfile = async () => {
        if (IS_READ_ONLY_MODE) {
            setAudioHealth(null);
            setVoiceProfile(null);
            setVoiceRefText('');
            setVoiceDisplayName('');
            setVoiceMessage(null);
            setVoiceProfileLoading(false);
            return;
        }

        try {
            setVoiceProfileLoading(true);
            const selectedProvider = getSettings().ttsProvider || 'kokoro';
            const [health, profile] = await Promise.all([
                getAudioHealth(selectedProvider),
                getNovelVoiceProfile(slug, selectedProvider)
            ]);
            setAudioHealth(health);
            setVoiceProfile(profile);
            setVoiceRefText(profile?.ref_text || '');
            setVoiceDisplayName(profile?.display_name || '');
            setVoiceMessage(null);
        } catch (err) {
            setAudioHealth(null);
            setVoiceProfile(null);
            setVoiceMessage(`Voice profile unavailable: ${err.message}`);
        } finally {
            setVoiceProfileLoading(false);
        }
    };

    const handleUpdate = async () => {
        setUpdating(true);
        setUpdateMessage(null);

        try {
            const trimmedSourceUrl = sourceUrlInput.trim();
            const result = await updateNovel(slug, trimmedSourceUrl || null);

            if (trimmedSourceUrl && novel?.source_toc_url !== trimmedSourceUrl) {
                setNovel((previous) => previous ? { ...previous, source_toc_url: trimmedSourceUrl } : previous);
            }

            if (result.job_id) {
                // Add job to global tracking
                addJob(result.job_id, {
                    status: 'pending',
                    current_chapter: 0,
                    total_chapters: result.missing_chapters?.length || 0,
                    novel_title: novel?.title,
                    error: null
                });
                setUpdateMessage(`Scraping ${result.missing_chapters?.length || 0} missing chapters...`);
            } else {
                setUpdateMessage(result.message);
            }
        } catch (err) {
            setUpdateMessage(`Error: ${err.message}`);
        } finally {
            setUpdating(false);
        }
    };

    const handleVoiceUpload = async () => {
        if (!voiceFile) {
            setVoiceMessage('Choose a reference voice file first.');
            return;
        }

        setVoiceSaving(true);
        setVoiceMessage(null);
        try {
            const selectedProvider = getSettings().ttsProvider || 'kokoro';
            const profile = await uploadNovelVoiceProfile(slug, {
                file: voiceFile,
                refText: voiceRefText,
                displayName: voiceDisplayName || voiceFile.name,
                provider: selectedProvider,
            });
            setVoiceProfile(profile);
            setVoiceFile(null);
            setVoiceMessage('Voice profile saved for this novel.');
        } catch (err) {
            setVoiceMessage(`Voice upload failed: ${err.message}`);
        } finally {
            setVoiceSaving(false);
        }
    };

    const handleVoiceDelete = async () => {
        setVoiceSaving(true);
        setVoiceMessage(null);
        try {
            const selectedProvider = getSettings().ttsProvider || 'kokoro';
            await deleteNovelVoiceProfile(slug, selectedProvider);
            setVoiceProfile(null);
            setVoiceRefText('');
            setVoiceDisplayName('');
            setVoiceFile(null);
            setVoiceMessage('Saved voice profile removed.');
        } catch (err) {
            setVoiceMessage(`Delete failed: ${err.message}`);
        } finally {
            setVoiceSaving(false);
        }
    };

    const toggleChapterSelection = (chapterNumber) => {
        setSelectedChapters((previous) =>
            previous.includes(chapterNumber)
                ? previous.filter((value) => value !== chapterNumber)
                : [...previous, chapterNumber].sort((left, right) => left - right)
        );
    };

    const getBatchTargetChapters = async () => {
        const chapterPoolResponse = await getChapters(slug, { sort: 'asc' });
        const chapterPool = chapterPoolResponse.chapters || [];

        if (audioGenerationMode === 'selected') {
            return chapterPool.filter((chapter) => selectedChapters.includes(chapter.chapter_number));
        }

        if (audioGenerationMode === 'range') {
            const start = Number.parseInt(rangeStart, 10);
            const end = Number.parseInt(rangeEnd, 10);

            if (Number.isNaN(start) || Number.isNaN(end)) {
                throw new Error('Enter both a valid start chapter and end chapter.');
            }

            if (end < start) {
                throw new Error('The end chapter must be greater than or equal to the start chapter.');
            }

            return chapterPool.filter(
                (chapter) => chapter.chapter_number >= start && chapter.chapter_number <= end
            );
        }

        return chapterPool;
    };

    const handleBulkAudioGeneration = async () => {
        setAudioBatchSubmitting(true);
        setAudioBatchMessage(null);

        try {
            const settings = getSettings();
            const selectedProvider = settings.ttsProvider || 'kokoro';

            if (selectedProvider === 'qwen3' && !voiceProfile?.exists) {
                throw new Error('Save a novel voice profile first before queueing Qwen audio.');
            }

            const targetChapters = await getBatchTargetChapters();
            if (targetChapters.length === 0) {
                throw new Error('No chapters match the current audio generation selection.');
            }

            const selectedVoice = selectedProvider === 'qwen3'
                ? (voiceProfile?.voice_name || 'novel-default')
                : selectedProvider === 'elevenlabs'
                    ? (settings.elevenlabsVoice || '')
                    : (settings.voice || 'af_heart');

            let queuedCount = 0;
            let existingCount = 0;
            let activeCount = 0;
            let pausedCount = 0;
            let failedCount = 0;

            for (let index = 0; index < targetChapters.length; index += 1) {
                const chapter = targetChapters[index];
                setAudioBatchMessage({
                    type: 'info',
                    text: `Queueing audio ${index + 1} of ${targetChapters.length}...`,
                });

                try {
                    const result = await generateChapterAudio(slug, chapter.chapter_number, selectedVoice, selectedProvider);
                    if (result.status === 'queued') {
                        queuedCount += 1;
                    } else if (result.status === 'exists') {
                        existingCount += 1;
                    } else if (result.status === 'already_generating') {
                        activeCount += 1;
                    } else if (result.status === 'paused') {
                        pausedCount += 1;
                    } else {
                        failedCount += 1;
                    }
                } catch (err) {
                    failedCount += 1;
                    console.error(`Failed to queue chapter ${chapter.chapter_number}`, err);
                }
            }

            const summaryParts = [];
            if (queuedCount > 0) summaryParts.push(`${queuedCount} queued`);
            if (activeCount > 0) summaryParts.push(`${activeCount} already generating`);
            if (pausedCount > 0) summaryParts.push(`${pausedCount} paused`);
            if (existingCount > 0) summaryParts.push(`${existingCount} already finished`);
            if (failedCount > 0) summaryParts.push(`${failedCount} failed`);

            setAudioBatchMessage({
                type: failedCount > 0 && queuedCount === 0 ? 'error' : 'success',
                text: summaryParts.length > 0
                    ? `Audio batch complete: ${summaryParts.join(', ')}.`
                    : 'No audio jobs were started.',
            });

            setSelectedChapters([]);
            await Promise.all([fetchChapters(), refreshAudioJobs?.()]);
        } catch (err) {
            setAudioBatchMessage({
                type: 'error',
                text: err.message || 'Audio generation could not be started.',
            });
        } finally {
            setAudioBatchSubmitting(false);
        }
    };

    const getChapterButtonClassName = (chapter) => {
        const classNames = ['chapter-btn'];

        if (chapter.has_audio) {
            classNames.push(chapter.audio_provider === 'qwen3' ? 'audio-qwen' : 'audio-kokoro');
        } else if (chapter.audio_status === 'generating' || chapter.audio_status === 'pending') {
            classNames.push('audio-pending');
        }

        if (selectedChapters.includes(chapter.chapter_number)) {
            classNames.push('selected');
        }

        return classNames.join(' ');
    };

    const formatRelativeTime = (dateString) => {
        if (!dateString) return 'Unknown';
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
        if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
        return `${Math.floor(diffDays / 365)} years ago`;
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
                    <Link to="/library" className="px-6 py-3 rounded-xl text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 shadow-md inline-block">
                        Return to Library
                    </Link>
                </div>
            </div>
        );
    }

    if (!novel) return null;

    const firstChapter = chapters.length > 0 ? Math.min(...chapters.map(c => c.chapter_number)) : 0;
    const currentSettings = getSettings();
    const selectedProvider = currentSettings.ttsProvider || 'kokoro';
    const qwenMode = selectedProvider === 'qwen3';
    const elevenlabsMode = selectedProvider === 'elevenlabs';
    const queuePanelClassName = qwenMode
        ? 'border-violet-500/20 border-l-4 border-l-violet-500'
        : elevenlabsMode
            ? 'border-amber-500/20 border-l-4 border-l-amber-500'
            : 'border-emerald-500/20 border-l-4 border-l-emerald-500';
    const modeChipClassName = qwenMode
        ? 'bg-violet-500/20 text-violet-800 dark:text-violet-300 shadow-sm'
        : elevenlabsMode
            ? 'bg-amber-500/20 text-amber-800 dark:text-amber-300 shadow-sm'
            : 'bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 shadow-sm';
    const dispatchButtonClassName = qwenMode
        ? 'bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500'
        : elevenlabsMode
            ? 'bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500'
            : 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500';
    const audioSummary = chapters.reduce((summary, chapter) => {
        if (!chapter.has_audio) {
            return summary;
        }
        if (chapter.audio_provider === 'qwen3') {
            summary.qwen3 += 1;
        } else if (chapter.audio_provider === 'elevenlabs') {
            summary.elevenlabs += 1;
        } else {
            summary.kokoro += 1;
        }
        return summary;
    }, { kokoro: 0, qwen3: 0, elevenlabs: 0 });

    return (
        <div className="min-h-screen p-4 md:p-8 pt-20 md:pt-8 flex flex-col gap-6 md:gap-8 max-w-[1600px] mx-auto relative z-10 w-full">
            {/* Solid mask to hide global body background image from index.css */}
            <div className="fixed inset-0 z-[-2] bg-[#f5f5f4] dark:bg-[#050308] transition-colors duration-700 pointer-events-none" />
            
            {/* The transparent artwork layer inherited from Library style */}
            <div className="novel-detail-bg-underlay novel-detail-base-bg" />

            <motion.div 
                className="w-full pb-16"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
            >
                {/* --- 1. Novel Header Banner --- */}
                <header className="glass rounded-[32px] p-6 md:p-10 border border-white/50 dark:border-white/10 shadow-xl dark:shadow-glass-lg mb-8 relative overflow-hidden flex flex-col md:flex-row gap-8 items-start md:items-center">
                    
                    {/* Subtle aesthetic glow mask behind the banner */}
                    <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-violet-500/10 dark:bg-violet-600/5 rounded-full blur-[100px] pointer-events-none -translate-y-1/2 translate-x-1/3" />

                    {/* Novel Cover */}
                    <div className="relative flex-shrink-0 w-[180px] md:w-[220px] shadow-2xl dark:shadow-glow-md rounded-2xl overflow-hidden self-center md:self-start border border-white/20 dark:border-white/5">
                        <div className="aspect-[3/4] bg-stone-200 dark:bg-black/40 flex items-center justify-center">
                            {novel.cover_url ? (
                                <img src={novel.cover_url} alt={novel.title} className="w-full h-full object-cover" />
                            ) : (
                                <BookOpen size={60} className="text-stone-400 dark:text-gray-600" />
                            )}
                        </div>
                        <div className="absolute top-3 left-3 px-2.5 py-1 bg-black/70 backdrop-blur-md rounded-lg text-[10px] uppercase font-bold text-white tracking-widest border border-white/10 shadow-sm">
                            {formatRelativeTime(novel.last_updated)}
                        </div>
                    </div>

                    {/* Novel Metadata */}
                    <div className="flex-1 flex flex-col min-w-0 z-10">
                        <h1 className="font-display text-4xl md:text-5xl font-bold text-stone-900 dark:text-white mb-4 tracking-tight drop-shadow-sm leading-tight max-w-2xl">
                            {novel.title}
                        </h1>

                        <div className="flex flex-wrap gap-2 mb-4">
                            {(novel.genres || '').split(',').map(genre => (
                                <span key={genre} className="px-3 py-1 bg-white/40 dark:bg-white/5 border border-stone-300/50 dark:border-white/10 rounded-full text-xs font-bold uppercase tracking-wider text-stone-600 dark:text-violet-200/80 shadow-sm backdrop-blur-sm">
                                    {genre.trim()}
                                </span>
                            ))}
                        </div>

                        <p className="text-stone-500 dark:text-violet-300/60 text-sm font-bold mb-4 uppercase tracking-widest">
                            <span className="text-stone-800 dark:text-white mr-2">{(novel.views || 0).toLocaleString()}</span> Views
                        </p>

                        <div className="glass-thin p-4 rounded-2xl bg-white/30 dark:bg-black/20 border-white/40 dark:border-white/5 mb-6">
                            <h3 className="text-xs font-bold text-stone-800 dark:text-violet-200 uppercase tracking-widest mb-2 flex items-center gap-2">
                                <Sparkles size={14} className="text-violet-500 dark:text-violet-400" />
                                Synopsis
                            </h3>
                            <p className="text-stone-700 dark:text-stone-300 text-sm leading-relaxed line-clamp-4 hover:line-clamp-none transition-all cursor-context-menu">
                                {novel.description || 'No description available for this novel.'}
                            </p>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex flex-wrap gap-3 items-stretch">
                            <Link 
                                to={`/novel/${slug}/chapter/${firstChapter}`} 
                                className="px-6 py-3 rounded-xl text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 dark:from-violet-600 dark:to-violet-600 dark:hover:from-violet-500 dark:hover:to-violet-500 shadow-md transition-all flex items-center gap-2 transform hover:-translate-y-0.5"
                            >
                                <Play size={16} fill="currentColor" />
                                Start Reading
                            </Link>
                            <button className="px-5 py-3 rounded-xl text-stone-700 dark:text-violet-100 font-bold text-sm bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-violet-500/20 border border-stone-300/50 dark:border-white/10 shadow-sm transition-all flex items-center gap-2 backdrop-blur-sm">
                                <BookOpen size={16} />
                                Continue
                            </button>
                            {!IS_READ_ONLY_MODE && (
                                <div className="flex flex-col gap-2 flex-1 min-w-[280px] md:min-w-[360px] md:max-w-xl ml-auto md:ml-0">
                                    <div className="flex gap-3 flex-wrap">
                                        <input
                                            type="url"
                                            value={sourceUrlInput}
                                            onChange={(event) => setSourceUrlInput(event.target.value)}
                                            placeholder="Paste the novel source URL for missing-chapter fetches"
                                            className="flex-1 min-w-[220px] px-4 py-3 rounded-xl text-sm font-medium text-stone-800 dark:text-violet-100 bg-white/55 dark:bg-white/5 border border-stone-300/50 dark:border-white/10 shadow-sm backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30"
                                        />
                                        <button
                                            className="px-5 py-3 rounded-xl text-stone-700 dark:text-violet-100 font-bold text-sm bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-violet-500/20 border border-stone-300/50 dark:border-white/10 shadow-sm transition-all flex items-center gap-2 backdrop-blur-sm"
                                            onClick={handleUpdate}
                                            disabled={updating}
                                        >
                                            {updating ? (
                                                <>
                                                    <Loader size={16} className="spin" />
                                                    Checking
                                                </>
                                            ) : (
                                                <>
                                                    <RefreshCw size={16} />
                                                    Fetch Updates
                                                </>
                                            )}
                                        </button>
                                    </div>
                                    <p className="text-xs text-stone-500 dark:text-stone-400 px-1">
                                        {novel?.source_toc_url
                                            ? 'This source URL is saved and will be reused for future missing-chapter fetches.'
                                            : 'Older novels do not have a saved source URL yet. Paste it once here and the app will save it for later update fetches.'}
                                    </p>
                                </div>
                            )}
                        </div>

                        {!IS_READ_ONLY_MODE && updateMessage && (
                            <div className={`mt-4 p-3 rounded-xl glass-thin text-sm font-medium flex items-center gap-2 ${updateMessage.includes('Error') ? 'bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400'}`}>
                                {updateMessage.includes('Error') ? null : <CheckCircle size={14} className="flex-shrink-0" />}
                                <span>{updateMessage}</span>
                            </div>
                        )}
                    </div>
                </header>

                {/* --- 2. Dynamic Session Interface (Provider Aware) --- */}
                {!IS_READ_ONLY_MODE && <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
                    
                    {/* Voice Profile Card (Qwen Only) */}
                    {qwenMode && (
                        <div className="glass rounded-3xl p-6 border border-amber-500/20 shadow-lg dark:shadow-glow-sm relative overflow-hidden">
                            <div className="absolute top-0 left-0 w-2 h-full bg-gradient-to-b from-amber-400 to-amber-600" />
                            
                            <div className="flex justify-between items-start mb-6">
                                <div>
                                    <h2 className="text-xl font-bold text-stone-900 dark:text-white mb-1 flex items-center gap-2">
                                        Novel Voice Profile
                                        <span className="px-2 py-0.5 rounded text-[9px] uppercase tracking-widest font-black bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                                            Qwen3 Enabled
                                        </span>
                                    </h2>
                                    <p className="text-sm text-stone-500 dark:text-stone-400">
                                        Establish a specific reference voice for all chapters in this novel.
                                    </p>
                                </div>
                            </div>

                            {voiceProfileLoading ? (
                                <div className="py-8 flex items-center justify-center text-stone-400">
                                    <Loader size={24} className="spin" />
                                </div>
                            ) : (
                                <div className="space-y-5">
                                    {voiceProfile?.exists && (
                                        <div className="glass-thin bg-amber-500/5 border-amber-500/20 p-4 rounded-xl">
                                            <div className="flex items-center gap-3 mb-2">
                                                <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-600 dark:text-amber-400">
                                                    <Volume2 size={16} />
                                                </div>
                                                <div>
                                                    <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">Active Profile</p>
                                                    <p className="text-sm font-bold text-stone-800 dark:text-white">
                                                        {voiceProfile.display_name || voiceProfile.voice_name || 'Novel Voice'}
                                                    </p>
                                                </div>
                                            </div>
                                            <p className="text-xs text-stone-600 dark:text-stone-400 bg-black/5 dark:bg-black/20 p-2 rounded">
                                                "{voiceProfile.ref_text || 'No transcript saved.'}"
                                            </p>
                                        </div>
                                    )}

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-xs font-bold text-stone-600 dark:text-stone-300 mb-1 pl-1">REFERENCE AUDIO (.wav)</label>
                                            <input
                                                type="file"
                                                accept=".wav,audio/wav"
                                                onChange={(e) => setVoiceFile(e.target.files?.[0] || null)}
                                                className="w-full text-sm text-stone-600 dark:text-stone-400 file:mr-3 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-amber-500/10 file:text-amber-700 dark:file:text-amber-400 hover:file:bg-amber-500/20 transition-all cursor-pointer"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-stone-600 dark:text-stone-300 mb-1 pl-1">PROFILE NAME</label>
                                            <input
                                                type="text"
                                                value={voiceDisplayName}
                                                onChange={(e) => setVoiceDisplayName(e.target.value)}
                                                placeholder="e.g. Fang Yuan Tone"
                                                className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-xl py-2 px-3 text-sm text-stone-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-amber-500/40"
                                            />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-bold text-stone-600 dark:text-stone-300 mb-1 pl-1">EXACT TRANSCRIPT</label>
                                            <textarea
                                                className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-xl py-2 px-3 text-sm text-stone-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-amber-500/40 min-h-[80px] voice-profile-textarea"
                                                value={voiceRefText}
                                                onChange={(e) => setVoiceRefText(e.target.value)}
                                                placeholder="Provide the exact text spoken in the audio for best results..."
                                            />
                                        </div>
                                    </div>

                                    <div className="flex gap-3">
                                        <button
                                            className="px-5 py-2 rounded-xl text-white font-bold text-sm bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 shadow-sm transition-all"
                                            onClick={handleVoiceUpload}
                                            disabled={voiceSaving}
                                        >
                                            {voiceSaving ? 'Saving...' : (voiceProfile?.exists ? 'Update Voice' : 'Establish Voice')}
                                        </button>
                                        {voiceProfile?.exists && (
                                            <button
                                                className="px-5 py-2 rounded-xl text-stone-700 dark:text-stone-300 font-bold text-sm bg-white/50 dark:bg-white/5 hover:bg-red-500/20 border border-stone-300/50 dark:border-white/10 transition-all"
                                                onClick={handleVoiceDelete}
                                                disabled={voiceSaving}
                                            >
                                                Delete
                                            </button>
                                        )}
                                    </div>

                                    {voiceMessage && (
                                        <div className={`p-3 rounded-xl glass-thin text-xs font-medium flex items-center gap-2 ${voiceMessage.includes('failed') ? 'bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400'}`}>
                                            {voiceMessage}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Audio Generation Terminal */}
                    <div className={`glass rounded-3xl p-6 border ${queuePanelClassName} shadow-lg ${!qwenMode ? 'lg:col-span-2 max-w-3xl mx-auto w-full' : ''}`}>
                        
                        <div className="flex justify-between items-start mb-6">
                            <div>
                                <h2 className="text-xl font-bold text-stone-900 dark:text-white mb-1">Queue Chapter Audio</h2>
                                <p className="text-sm text-stone-500 dark:text-stone-400 max-w-sm">
                                    {qwenMode 
                                        ? 'Select chapters to synthesize using the established novel voice profile above.' 
                                        : elevenlabsMode
                                            ? 'Select chapters to synthesize using your selected ElevenLabs voice.'
                                            : 'Select chapters to synthesize using your default Kokoro reader settings.'}
                                </p>
                            </div>

                            {/* Audio DB Stats Pill */}
                            <div className="flex gap-2">
                                <div className="px-3 py-1.5 rounded-full bg-slate-200/50 dark:bg-slate-800/50 border border-slate-300/50 dark:border-slate-600/50 flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-300"></div>
                                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-widest">{audioSummary.kokoro}</span>
                                </div>
                                <div className="px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-amber-500"></div>
                                    <span className="text-xs font-bold text-amber-700 dark:text-amber-400 uppercase tracking-widest">{audioSummary.qwen3}</span>
                                </div>
                                <div className="px-3 py-1.5 rounded-full bg-orange-500/10 border border-orange-500/20 flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-orange-500"></div>
                                    <span className="text-xs font-bold text-orange-700 dark:text-orange-400 uppercase tracking-widest">{audioSummary.elevenlabs}</span>
                                </div>
                            </div>
                        </div>

                        {/* Mode Switcher */}
                        <div className="flex bg-white/40 dark:bg-black/20 p-1 rounded-xl border border-stone-300/50 dark:border-white/5 mb-6 max-w-max">
                            {['selected', 'range', 'all'].map((mode) => (
                                <button
                                    key={mode}
                                    type="button"
                                    className={`px-4 py-2 rounded-lg text-sm font-bold capitalize transition-all ${audioGenerationMode === mode ? modeChipClassName : 'text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200'}`}
                                    onClick={() => setAudioGenerationMode(mode)}
                                >
                                    {mode}
                                </button>
                            ))}
                        </div>

                        {/* Mode Logic */}
                        <div className="min-h-[80px] mb-6">
                            {audioGenerationMode === 'selected' && (
                                <div className="glass-thin p-4 rounded-xl bg-white/20 dark:bg-white/5 border-white/40 dark:border-white/5">
                                    <p className="text-sm text-stone-600 dark:text-stone-300 mb-2">Tap chapter tiles in the grid below to explicitly select them for synthesis.</p>
                                    <div className="flex justify-between items-center text-xs font-bold">
                                        <span className="text-stone-800 dark:text-white bg-black/5 dark:bg-black/20 px-2 py-1 rounded">{selectedChapters.length} Selected</span>
                                        <button className="text-red-500 hover:text-red-600 transition-colors uppercase tracking-widest" onClick={() => setSelectedChapters([])} disabled={selectedChapters.length === 0}>Clear All</button>
                                    </div>
                                </div>
                            )}

                            {audioGenerationMode === 'range' && (
                                <div className="glass-thin p-4 rounded-xl bg-white/20 dark:bg-white/5 border-white/40 dark:border-white/5 flex items-center gap-4">
                                    <div className="flex-1">
                                        <label className="block text-[10px] uppercase font-bold text-stone-500 dark:text-stone-400 mb-1 pl-1">Start Chapter</label>
                                        <input type="number" min="1" value={rangeStart} onChange={(e) => setRangeStart(e.target.value)} placeholder="1" className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-lg py-2 px-3 text-sm text-stone-800 dark:text-white font-bold text-center focus:outline-none focus:ring-2 focus:ring-violet-500/40" />
                                    </div>
                                    <span className="text-stone-400 font-black">-</span>
                                    <div className="flex-1">
                                        <label className="block text-[10px] uppercase font-bold text-stone-500 dark:text-stone-400 mb-1 pl-1">End Chapter</label>
                                        <input type="number" min="1" value={rangeEnd} onChange={(e) => setRangeEnd(e.target.value)} placeholder={chapters.at(-1)?.chapter_number || '100'} className="w-full bg-white/50 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-lg py-2 px-3 text-sm text-stone-800 dark:text-white font-bold text-center focus:outline-none focus:ring-2 focus:ring-violet-500/40" />
                                    </div>
                                </div>
                            )}

                            {audioGenerationMode === 'all' && (
                                <div className="glass-thin p-4 rounded-xl bg-white/20 dark:bg-white/5 border-white/40 dark:border-white/5">
                                    <p className="text-sm text-stone-600 dark:text-stone-300">Queue audio generation for the entire novel.</p>
                                    <p className="text-xs font-bold text-stone-800 dark:text-white mt-2 bg-black/5 dark:bg-black/20 px-2 py-1 rounded inline-block">Total Payload: {novel.chapter_count || chapters.length} Chapters</p>
                                </div>
                            )}
                        </div>

                        {/* Submit Actions */}
                        <div className="flex items-center gap-4">
                            <button
                                className={`px-6 py-3 rounded-xl text-white font-bold text-sm shadow-md transition-all flex items-center gap-2 transform hover:-translate-y-0.5 ${dispatchButtonClassName}`}
                                onClick={handleBulkAudioGeneration}
                                disabled={audioBatchSubmitting || (qwenMode && !voiceProfile?.exists)}
                            >
                                {audioBatchSubmitting ? <><Loader size={16} className="spin" /> Sending to API...</> : <><Play size={16} fill="currentColor" /> Dispatch Jobs</>}
                            </button>
                            <span className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                                {qwenMode
                                    ? (voiceProfile?.exists ? 'Voice Ready' : 'Awaiting Voice Profile')
                                    : elevenlabsMode
                                        ? `Using Voice: ${currentSettings.elevenlabsVoice || 'Auto-select'}`
                                        : `Using Setting: ${currentSettings.voice || 'af_heart'}`}
                            </span>
                        </div>

                        {audioBatchMessage && (
                            <div className={`mt-4 p-3 rounded-xl glass-thin text-xs font-medium flex items-center gap-2 ${audioBatchMessage.type === 'error' ? 'bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400'}`}>
                                {audioBatchMessage.text}
                            </div>
                        )}
                    </div>
                </div>}

                {/* --- 3. Chapter Grid & Explorer --- */}
                <div className="glass rounded-[32px] p-6 md:p-8 border border-white/50 dark:border-white/10 shadow-lg relative min-h-[500px]">
                    
                    {/* Controls Bar */}
                    <div className="flex flex-col md:flex-row justify-between items-center gap-4 mb-8">
                        <div className="w-full md:max-w-xs relative">
                            <input
                                type="text"
                                className="w-full bg-white/40 dark:bg-black/20 border border-stone-300/50 dark:border-white/10 rounded-full py-2.5 px-5 text-sm font-bold text-stone-800 dark:text-white placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-all font-display tracking-wide shadow-sm"
                                placeholder="Search chapters..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>

                        <div className="flex bg-white/40 dark:bg-black/20 p-1 rounded-full border border-stone-300/50 dark:border-white/5 shadow-sm">
                            <button
                                className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${sortOrder === 'asc' ? 'bg-white dark:bg-white/10 text-stone-800 dark:text-white shadow-sm' : 'text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200'}`}
                                onClick={() => setSortOrder('asc')}
                            >
                                First - Last
                            </button>
                            <button
                                className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${sortOrder === 'desc' ? 'bg-white dark:bg-white/10 text-stone-800 dark:text-white shadow-sm' : 'text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200'}`}
                                onClick={() => setSortOrder('desc')}
                            >
                                Last - First
                            </button>
                        </div>
                    </div>

                    {/* Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                        {chapters.map(chapter => {
                            let baseClasses = "glass-thin flex flex-col items-center justify-center py-4 px-2 rounded-2xl border transition-all text-center group cursor-pointer hover:shadow-lg hover:-translate-y-1 overflow-hidden relative min-h-[100px] ";
                            const isGenerating = chapter.audio_status === 'generating' || chapter.audio_status === 'pending';
                            const isPaused = chapter.audio_status === 'paused';
                            const isCancelled = chapter.audio_status === 'cancelled';
                            
                            if (selectedChapters.includes(chapter.chapter_number)) {
                                baseClasses += "border-violet-500/50 bg-violet-500/10 ring-2 ring-violet-500/20 ";
                            } else if (chapter.has_audio) {
                                if (chapter.audio_provider === 'qwen3') {
                                    baseClasses += "border-amber-400/40 dark:border-amber-500/30 bg-gradient-to-br from-amber-500/5 to-transparent ";
                                } else if (chapter.audio_provider === 'elevenlabs') {
                                    baseClasses += "border-orange-400/40 dark:border-orange-500/30 bg-gradient-to-br from-orange-500/5 to-transparent ";
                                } else {
                                    baseClasses += "border-slate-300/50 dark:border-slate-500/30 bg-gradient-to-br from-slate-400/5 to-transparent ";
                                }
                            } else if (isGenerating) {
                                baseClasses += "border-dashed border-blue-400/50 dark:border-blue-500/40 bg-blue-500/5 ";
                            } else if (isPaused) {
                                baseClasses += "border-dashed border-amber-400/50 dark:border-amber-500/40 bg-amber-500/5 ";
                            } else if (isCancelled) {
                                baseClasses += "border-dashed border-rose-400/50 dark:border-rose-500/40 bg-rose-500/5 ";
                            } else {
                                baseClasses += "border-stone-200/50 dark:border-white/5 hover:border-violet-400/30 dark:hover:border-violet-500/30 bg-white/20 dark:bg-black/20 ";
                            }

                            return audioGenerationMode === 'selected' ? (
                                <button
                                    key={chapter.id}
                                    type="button"
                                    className={baseClasses}
                                    onClick={() => toggleChapterSelection(chapter.chapter_number)}
                                >
                                    <span className="text-xl font-display font-bold text-stone-800 dark:text-white mb-1 group-hover:scale-110 transition-transform">{chapter.chapter_number}</span>
                                    
                                    {chapter.has_audio && (
                                        <span className={`text-[9px] uppercase font-black tracking-widest ${chapter.audio_provider === 'qwen3' ? 'text-amber-600 dark:text-amber-400' : chapter.audio_provider === 'elevenlabs' ? 'text-orange-600 dark:text-orange-400' : 'text-slate-500 dark:text-slate-400'}`}>
                                            {chapter.audio_provider === 'qwen3' ? 'Qwen TTS' : chapter.audio_provider === 'elevenlabs' ? 'ElevenLabs TTS' : 'Kokoro TTS'}
                                        </span>
                                    )}
                                    {!chapter.has_audio && isGenerating && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-blue-500 dark:text-blue-400 flex items-center gap-1">
                                            <Loader size={8} className="spin" /> Generating
                                        </span>
                                    )}
                                    {!chapter.has_audio && isPaused && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-amber-600 dark:text-amber-400">
                                            Paused
                                        </span>
                                    )}
                                    {!chapter.has_audio && isCancelled && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-rose-600 dark:text-rose-400">
                                            Cancelled
                                        </span>
                                    )}
                                    {!chapter.has_audio && !isGenerating && !isPaused && !isCancelled && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-stone-400 dark:text-stone-500">
                                            Text Only
                                        </span>
                                    )}
                                </button>
                            ) : (
                                <Link
                                    key={chapter.id}
                                    to={`/novel/${slug}/chapter/${chapter.chapter_number}`}
                                    className={baseClasses}
                                >
                                    <span className="text-xl font-display font-bold text-stone-800 dark:text-white mb-1 group-hover:scale-110 transition-transform">{chapter.chapter_number}</span>
                                    
                                    {chapter.has_audio && (
                                        <span className={`text-[9px] uppercase font-black tracking-widest ${chapter.audio_provider === 'qwen3' ? 'text-amber-600 dark:text-amber-400' : chapter.audio_provider === 'elevenlabs' ? 'text-orange-600 dark:text-orange-400' : 'text-slate-500 dark:text-slate-400'}`}>
                                            {chapter.audio_provider === 'qwen3' ? 'Qwen TTS' : chapter.audio_provider === 'elevenlabs' ? 'ElevenLabs TTS' : 'Kokoro TTS'}
                                        </span>
                                    )}
                                    {!chapter.has_audio && isGenerating && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-blue-500 dark:text-blue-400 flex items-center gap-1">
                                            <Loader size={8} className="spin" /> Generating
                                        </span>
                                    )}
                                    {!chapter.has_audio && isPaused && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-amber-600 dark:text-amber-400">
                                            Paused
                                        </span>
                                    )}
                                    {!chapter.has_audio && isCancelled && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-rose-600 dark:text-rose-400">
                                            Cancelled
                                        </span>
                                    )}
                                    {!chapter.has_audio && !isGenerating && !isPaused && !isCancelled && (
                                        <span className="text-[9px] uppercase font-black tracking-widest text-stone-400 dark:text-stone-500">
                                            Text Only
                                        </span>
                                    )}
                                </Link>
                            )
                        })}

                        {chapters.length === 0 && (
                            <div className="col-span-full py-20 flex flex-col items-center justify-center text-center">
                                <BookOpen size={48} className="text-stone-300 dark:text-stone-700 mb-4" />
                                <h3 className="text-lg font-bold text-stone-800 dark:text-white mb-1">Library Empty</h3>
                                <p className="text-sm text-stone-500">No chapters have been scraped for this novel yet.</p>
                            </div>
                        )}
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

export default NovelDetail;
