import { useState, useRef, useEffect, useCallback } from 'react';
import { Play, Pause, Volume2, VolumeX, X, Loader, ChevronUp, ChevronDown, StopCircle } from 'lucide-react';
import { getAudioStatus, generateChapterAudio, getAudioStreamUrl } from '../../services/api';
import { useScrapingJobs } from '../../context/ScrapingContext';
import { IS_READ_ONLY_MODE } from '../../config/runtime';
import './AudioPlayer.css';

function AudioPlayer({ novelSlug, chapterNumber, chapterTitle, settings, onClose, onTimeUpdate, onSpeedChange, onAudioReady }) {
    const {
        pauseAudioGeneration,
        resumeAudioGeneration,
        cancelAudioGeneration
    } = useScrapingJobs();
    const audioRef = useRef(null);
    const pollIntervalRef = useRef(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [audioReady, setAudioReady] = useState(false);
    const [audioUrl, setAudioUrl] = useState(null);
    const [progress, setProgress] = useState(0);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [speed, setSpeed] = useState(settings?.ttsSpeed || 1.0);
    const [isMuted, setIsMuted] = useState(false);
    const [isMinimized, setIsMinimized] = useState(false);
    const [error, setError] = useState(null);
    const [generationStatus, setGenerationStatus] = useState(null);
    const [generationInfo, setGenerationInfo] = useState(null);

    const isAudioAvailable = useCallback((status) => (
        Boolean(status?.exists || status?.audio_only || status?.status === 'completed')
    ), []);

    const isGenerationPaused = useCallback((status) => (
        Boolean(status?.status === 'paused' || status?.job_status === 'paused')
    ), []);

    const isGenerationCancelled = useCallback((status) => (
        Boolean(status?.status === 'cancelled' || status?.job_status === 'cancelled')
    ), []);

    const isGenerationFailed = useCallback((status) => (
        Boolean(status?.status === 'failed' || status?.job_status === 'failed')
    ), []);

    const canRetryGeneration = useCallback((status) => (
        isGenerationFailed(status) || isGenerationCancelled(status)
    ), [isGenerationCancelled, isGenerationFailed]);

    const isGenerationActive = useCallback((status) => (
        Boolean(status?.generating || status?.status === 'generating' || status?.job_status === 'generating')
    ), []);

    const hasGenerationJob = useCallback((status) => (
        isGenerationActive(status) || isGenerationPaused(status)
    ), [isGenerationActive, isGenerationPaused]);

    const loadAudio = useCallback((slug, chapter) => {
        const url = `${getAudioStreamUrl(slug, chapter)}?t=${Date.now()}`;
        setAudioUrl(url);
        setAudioReady(true);
        setIsLoading(false);
        setGenerationStatus(null);
        setGenerationInfo(null);
        if (onAudioReady) {
            setTimeout(() => onAudioReady(), 500);
        }
    }, [onAudioReady]);

    const stopPolling = useCallback(() => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    const buildGenerationMessage = useCallback((status) => {
        if (!status) {
            return null;
        }
        if (isGenerationPaused(status)) {
            return status.message || 'Generation paused';
        }
        if (isGenerationCancelled(status)) {
            return status.message || 'Generation cancelled';
        }
        if (status.message) {
            return status.message;
        }
        if (status.completed_chunks && status.total_chunks) {
            return `Processed ${status.completed_chunks} of ${status.total_chunks} chunks`;
        }
        if (isGenerationActive(status)) {
            return 'Generating audio...';
        }
        return null;
    }, [isGenerationActive, isGenerationCancelled, isGenerationPaused]);

    const applyStatus = useCallback((status) => {
        setGenerationInfo(status || null);

        if (isAudioAvailable(status)) {
            loadAudio(novelSlug, chapterNumber);
            return 'ready';
        }

        if (status?.error) {
            setError(status.error);
            setGenerationStatus(null);
            setIsLoading(false);
            return 'error';
        }

        if (isGenerationCancelled(status)) {
            setGenerationStatus(buildGenerationMessage(status));
            setIsLoading(false);
            return 'cancelled';
        }

        if (isGenerationPaused(status)) {
            setGenerationStatus(buildGenerationMessage(status));
            setIsLoading(false);
            return 'paused';
        }

        if (isGenerationActive(status)) {
            setGenerationStatus(buildGenerationMessage(status));
            setIsLoading(false);
            return 'generating';
        }

        setGenerationStatus(null);
        setIsLoading(false);
        return 'idle';
    }, [
        buildGenerationMessage,
        chapterNumber,
        isAudioAvailable,
        isGenerationActive,
        isGenerationCancelled,
        isGenerationPaused,
        loadAudio,
        novelSlug
    ]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => stopPolling();
    }, [stopPolling]);

    // Check audio status on mount (but don't auto-generate)
    useEffect(() => {
        checkAudioStatus();
    }, [novelSlug, chapterNumber]);

    // Update playback speed when settings change
    useEffect(() => {
        if (audioRef.current && settings?.ttsSpeed) {
            setSpeed(settings.ttsSpeed);
            audioRef.current.playbackRate = settings.ttsSpeed;
        }
    }, [settings?.ttsSpeed]);

    const checkAudioStatus = async () => {
        setIsLoading(true);
        setError(null);

        try {
            const status = await getAudioStatus(novelSlug, chapterNumber);
            const state = applyStatus(status);
            if (state === 'generating' || state === 'paused') {
                pollForCompletion();
            }
        } catch (err) {
            console.error('Audio check error:', err);
            setError('Failed to check audio status');
            setIsLoading(false);
        }
    };

    const startAudioGeneration = async ({ force = false } = {}) => {
        if (IS_READ_ONLY_MODE) {
            setIsLoading(false);
            return;
        }

        setIsLoading(true);
        setError(null);
        setGenerationStatus('Starting TTS generation...');

        try {
            const provider = settings?.ttsProvider || 'kokoro';
            const voice = provider === 'elevenlabs'
                ? (settings?.elevenlabsVoice || '')
                : (settings?.voice || 'af_heart');
            const data = await generateChapterAudio(novelSlug, chapterNumber, voice, provider, { force });

            if (data.status === 'exists') {
                loadAudio(novelSlug, chapterNumber);
            } else if (data.status === 'queued' || data.status === 'already_generating' || data.status === 'paused') {
                const status = await getAudioStatus(novelSlug, chapterNumber).catch(() => null);
                if (status) {
                    const state = applyStatus(status);
                    if (state === 'generating' || state === 'paused') {
                        pollForCompletion();
                    }
                } else {
                    setGenerationInfo((previous) => previous || { progress: 0 });
                    setGenerationStatus(data.message || 'Generating audio...');
                    setIsLoading(false);
                    pollForCompletion();
                }
            } else {
                setError(data.message || 'Generation failed');
                setIsLoading(false);
            }
        } catch (err) {
            console.error('Audio generation error:', err);
            setError('Failed to start audio generation');
            setIsLoading(false);
        }
    };

    const handleRetry = async () => {
        if (canRetryGeneration(generationInfo)) {
            await startAudioGeneration({ force: true });
            return;
        }

        await checkAudioStatus();
    };

    const pollForCompletion = () => {
        stopPolling();

        pollIntervalRef.current = setInterval(async () => {
            try {
                const status = await getAudioStatus(novelSlug, chapterNumber);
                const state = applyStatus(status);
                if (state === 'ready' || state === 'error' || state === 'idle') {
                    stopPolling();
                }
            } catch {
                stopPolling();
                setError('Connection lost');
                setIsLoading(false);
            }
        }, 2000);
    };

    const handlePauseResumeGeneration = async () => {
        try {
            if (isGenerationPaused(generationInfo)) {
                const updated = await resumeAudioGeneration(novelSlug, chapterNumber);
                setGenerationInfo((prev) => ({ ...(prev || {}), ...(updated || {}), status: 'generating', job_status: 'generating' }));
                setGenerationStatus(updated?.message || 'Generating audio...');
                pollForCompletion();
                return;
            }

            const updated = await pauseAudioGeneration(novelSlug, chapterNumber);
            setGenerationInfo((prev) => ({ ...(prev || {}), ...(updated || {}), status: 'paused', job_status: 'paused' }));
            setGenerationStatus(updated?.message || 'Generation paused');
        } catch (err) {
            console.error('Pause/resume generation error:', err);
            setError(err?.message || 'Failed to update generation state');
        }
    };

    const handleCancelGeneration = async () => {
        try {
            const updated = await cancelAudioGeneration(novelSlug, chapterNumber);
            stopPolling();
            setGenerationInfo((prev) => ({ ...(prev || {}), ...(updated || {}), status: 'cancelled', job_status: 'cancelled' }));
            setGenerationStatus(updated?.message || 'Generation cancelled');
            setIsLoading(false);
        } catch (err) {
            console.error('Cancel generation error:', err);
            setError(err?.message || 'Failed to cancel generation');
        }
    };

    // Audio event handlers
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;

        const handleTimeUpdate = () => {
            const time = audio.currentTime;
            const dur = audio.duration;

            setCurrentTime(time);
            setProgress((time / dur) * 100);

            if (onTimeUpdate && dur && !isNaN(time)) {
                onTimeUpdate(time, audio.playbackRate);
            }
        };

        const handleLoadedMetadata = () => {
            setDuration(audio.duration);
        };

        const handleEnded = () => {
            setIsPlaying(false);
            setProgress(0);
        };

        audio.addEventListener('timeupdate', handleTimeUpdate);
        audio.addEventListener('loadedmetadata', handleLoadedMetadata);
        audio.addEventListener('ended', handleEnded);

        return () => {
            audio.removeEventListener('timeupdate', handleTimeUpdate);
            audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
            audio.removeEventListener('ended', handleEnded);
        };
    }, [audioUrl, onTimeUpdate]);

    const togglePlay = () => {
        if (!audioRef.current) return;

        if (isPlaying) {
            audioRef.current.pause();
        } else {
            audioRef.current.play().catch(err => {
                console.error('Play error:', err);
                setError('Failed to play audio');
            });
        }
        setIsPlaying(!isPlaying);
    };

    const handleSeek = (e) => {
        if (!audioRef.current || !duration) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        const newTime = pos * duration;
        audioRef.current.currentTime = newTime;
        setCurrentTime(newTime);
        setProgress(pos * 100);
    };

    const changeSpeed = () => {
        const speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
        const currentIdx = speeds.indexOf(speed);
        const nextSpeed = speeds[(currentIdx + 1) % speeds.length];
        setSpeed(nextSpeed);
        if (audioRef.current) {
            audioRef.current.playbackRate = nextSpeed;
        }
        if (onSpeedChange) {
            onSpeedChange(nextSpeed);
        }
    };

    const toggleMute = () => {
        if (audioRef.current) {
            audioRef.current.muted = !isMuted;
            setIsMuted(!isMuted);
        }
    };

    const formatTime = (seconds) => {
        if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const generationProgress = Math.max(0, Math.min(100, generationInfo?.progress || 0));
    const activeChunk = generationInfo?.current_chunk || generationInfo?.completed_chunks || 0;
    const totalChunks = generationInfo?.total_chunks || 0;
    const progressCaption = totalChunks
        ? `${Math.min(generationInfo?.completed_chunks || 0, totalChunks)} / ${totalChunks} chunks processed`
        : 'Waiting for chunk progress...';

    if (isMinimized) {
        return (
            <div className="fixed bottom-4 md:bottom-8 right-4 md:right-8 z-[100] flex items-center gap-3 p-2 pr-4 glass rounded-full border border-white/20 dark:border-white/10 shadow-2xl animate-in slide-in-from-bottom-5">
                <button 
                    className="w-10 h-10 rounded-full flex items-center justify-center bg-white/50 dark:bg-white/5 hover:bg-stone-200 dark:hover:bg-white/10 transition-all text-stone-600 dark:text-stone-300 border border-stone-200/50 dark:border-white/10" 
                    onClick={() => setIsMinimized(false)}
                >
                    <ChevronUp size={18} />
                </button>
                <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-widest text-violet-600 dark:text-violet-400">Playing</span>
                    <span className="text-sm font-medium text-stone-800 dark:text-stone-200 max-w-[120px] truncate">
                        {chapterTitle || `Chapter ${chapterNumber}`}
                    </span>
                </div>
                <button
                    className={`w-10 h-10 ml-2 rounded-full flex items-center justify-center transition-all shadow-md text-white ${audioReady ? 'bg-gradient-to-r from-violet-500 to-indigo-500 hover:scale-105' : 'bg-stone-400 dark:bg-stone-600 cursor-not-allowed hidden'}`}
                    onClick={togglePlay}
                    disabled={!audioReady}
                >
                    {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-1" />}
                </button>
            </div>
        );
    }

    return (
        <div className="fixed bottom-4 md:bottom-8 right-4 md:right-8 z-[100] w-[calc(100%-32px)] md:w-[360px] glass rounded-[32px] overflow-hidden border border-white/20 dark:border-white/10 shadow-2xl flex flex-col animate-in slide-in-from-bottom-8">
            {audioUrl && (
                <audio
                    ref={audioRef}
                    src={audioUrl}
                    preload="auto"
                    crossOrigin="anonymous"
                />
            )}

            <div className="flex items-center justify-between p-4 md:p-5 border-b border-stone-200/50 dark:border-white/10 bg-white/40 dark:bg-black/20">
                <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-violet-600 dark:text-violet-400 mb-0.5">Audio Player</span>
                    <span className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate max-w-[200px]">
                        {chapterTitle || `Chapter ${chapterNumber}`}
                    </span>
                </div>
                <div className="flex gap-1">
                    <button 
                        className="w-8 h-8 rounded-full flex items-center justify-center text-stone-500 hover:bg-white/50 dark:hover:bg-white/10 transition-all" 
                        onClick={() => setIsMinimized(true)}
                    >
                        <ChevronDown size={16} />
                    </button>
                    <button 
                        className="w-8 h-8 rounded-full flex items-center justify-center text-stone-500 hover:bg-white/50 dark:hover:bg-white/10 transition-all" 
                        onClick={onClose}
                    >
                        <X size={16} />
                    </button>
                </div>
            </div>

            <div className="p-5 flex flex-col">
                {isLoading ? (
                    <div className="flex flex-col items-center justify-center py-8 gap-3 text-stone-500 dark:text-stone-400">
                        <Loader size={24} className="spin text-violet-500" />
                        <span className="text-sm font-medium">{generationStatus || 'Loading audio...'}</span>
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center py-6 gap-3 text-red-500 text-center">
                        <span className="text-sm font-medium flex-1 px-4">{error}</span>
                        <button className="px-4 py-2 mt-2 rounded-xl text-xs font-bold bg-white/50 dark:bg-white/10 hover:bg-white/80 dark:hover:bg-white/20 text-stone-700 dark:text-stone-300 transition-all border border-stone-200/50 dark:border-white/10" onClick={handleRetry}>
                            {canRetryGeneration(generationInfo) ? 'Retry Generation' : 'Retry Connection'}
                        </button>
                    </div>
                ) : !audioReady && hasGenerationJob(generationInfo) ? (
                    <div className="flex flex-col gap-4">
                        <div className="flex items-center gap-2 text-stone-800 dark:text-stone-200 font-medium text-sm">
                            {isGenerationPaused(generationInfo)
                                ? <Pause size={16} className="text-amber-500" />
                                : <Loader size={16} className="spin text-violet-500" />}
                            <span>{generationStatus || 'Generating audio...'}</span>
                        </div>

                        <div className="h-2 w-full bg-stone-200/50 dark:bg-white/5 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 transition-all duration-300"
                                style={{ width: `${generationProgress}%` }}
                            />
                        </div>

                        <div className="flex justify-between text-xs font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                            <span>{progressCaption}</span>
                            <span className="text-violet-600 dark:text-violet-400">{Math.round(generationProgress)}%</span>
                        </div>

                        <div className="grid grid-cols-2 gap-2 mt-2 border-t border-stone-200/50 dark:border-white/10 pt-4">
                            <div className="flex flex-col bg-white/40 dark:bg-white/5 p-2 rounded-xl border border-stone-200/50 dark:border-white/5">
                                <span className="text-[10px] uppercase font-bold text-stone-400">Current Iteration</span>
                                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{activeChunk ? `Chunk ${activeChunk}` : 'Preparing...'}</span>
                            </div>
                            <div className="flex flex-col bg-white/40 dark:bg-white/5 p-2 rounded-xl border border-stone-200/50 dark:border-white/5">
                                <span className="text-[10px] uppercase font-bold text-stone-400">Time Elapsed</span>
                                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{generationInfo?.elapsed_seconds ? formatTime(generationInfo.elapsed_seconds) : '--:--'}</span>
                            </div>
                            <div className="flex flex-col bg-white/40 dark:bg-white/5 p-2 rounded-xl border border-stone-200/50 dark:border-white/5">
                                <span className="text-[10px] uppercase font-bold text-stone-400">Avg / Chunk</span>
                                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{generationInfo?.average_chunk_seconds ? `${generationInfo.average_chunk_seconds.toFixed(1)}s` : '--'}</span>
                            </div>
                            <div className="flex flex-col bg-white/40 dark:bg-white/5 p-2 rounded-xl border border-stone-200/50 dark:border-white/5">
                                <span className="text-[10px] uppercase font-bold text-stone-400">ETA</span>
                                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{generationInfo?.estimated_remaining_seconds ? formatTime(generationInfo.estimated_remaining_seconds) : '--:--'}</span>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 mt-2">
                            <button
                                className="w-full py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-violet-500 to-indigo-500 text-white hover:from-violet-400 hover:to-indigo-400 transition-all border border-transparent"
                                onClick={handlePauseResumeGeneration}
                            >
                                {isGenerationPaused(generationInfo) ? 'Resume' : 'Pause'} Generation
                            </button>
                            <button
                                className="w-full py-2.5 rounded-xl text-xs font-bold bg-white/50 dark:bg-white/5 hover:bg-stone-200 dark:hover:bg-white/10 text-stone-600 dark:text-stone-400 transition-all border border-stone-200/50 dark:border-white/5 flex items-center justify-center gap-1"
                                onClick={handleCancelGeneration}
                            >
                                <StopCircle size={14} />
                                Cancel
                            </button>
                            <button className="col-span-2 w-full py-2.5 rounded-xl text-xs font-bold bg-white/50 dark:bg-white/5 hover:bg-stone-200 dark:hover:bg-white/10 text-stone-600 dark:text-stone-400 transition-all border border-stone-200/50 dark:border-white/5" onClick={checkAudioStatus}>
                                Refresh Status
                            </button>
                        </div>
                    </div>
                ) : !audioReady ? (
                    <div className="flex flex-col items-center justify-center py-6 gap-4">
                        <span className="text-sm font-medium text-stone-600 dark:text-stone-400">{IS_READ_ONLY_MODE ? 'Audio not available yet' : 'Audio not generated yet'}</span>
                        {!IS_READ_ONLY_MODE && (
                            <button className="px-6 py-2.5 rounded-xl text-white font-bold text-sm bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 shadow-md transition-all" onClick={startAudioGeneration}>
                                Generate Now
                            </button>
                        )}
                    </div>
                ) : (
                    <>
                        <div 
                            className="h-2 w-full bg-stone-200/80 dark:bg-white/10 rounded-full overflow-hidden cursor-pointer relative group" 
                            onClick={handleSeek}
                        >
                            <div
                                className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 transition-all duration-100 ease-linear rounded-r-full group-hover:from-violet-400 group-hover:to-indigo-400"
                                style={{ width: `${progress}%` }}
                            />
                        </div>

                        <div className="flex justify-between mt-2 text-[11px] font-bold text-stone-500 dark:text-stone-400 tracking-wider">
                            <span>{formatTime(currentTime)}</span>
                            <span>{formatTime(duration)}</span>
                        </div>

                        <div className="flex items-center justify-between mt-6 px-2">
                            <button 
                                className="w-10 h-10 rounded-full flex items-center justify-center text-stone-500 hover:bg-white/50 dark:hover:bg-white/10 hover:text-stone-800 dark:hover:text-stone-200 transition-all" 
                                onClick={toggleMute}
                            >
                                {isMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
                            </button>

                            <button
                                className={`w-14 h-14 rounded-full flex items-center justify-center transition-all bg-gradient-to-r from-violet-500 to-indigo-500 text-white shadow-lg ${audioReady ? 'hover:scale-105 hover:shadow-violet-500/25' : 'opacity-50 cursor-not-allowed'}`}
                                onClick={togglePlay}
                                disabled={!audioReady}
                            >
                                {isPlaying ? <Pause size={24} /> : <Play size={24} className="ml-1" />}
                            </button>

                            <button 
                                className="w-12 h-8 rounded-xl flex items-center justify-center text-xs font-bold text-stone-600 dark:text-stone-300 bg-white/50 dark:bg-white/5 hover:bg-white/80 dark:hover:bg-white/10 transition-all border border-stone-200/50 dark:border-white/10" 
                                onClick={changeSpeed}
                            >
                                {speed}x
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

export default AudioPlayer;
