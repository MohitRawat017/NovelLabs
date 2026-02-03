import { useState, useRef, useEffect } from 'react';
import { Play, Pause, Volume2, VolumeX, X, Loader, ChevronUp, ChevronDown } from 'lucide-react';
import './AudioPlayer.css';

// Use environment variable for production, fallback to localhost for development
const API_URL = import.meta.env.VITE_API_URL?.replace(/\/api$/, '') || 'http://localhost:8001';

function AudioPlayer({ novelSlug, chapterNumber, chapterTitle, settings, onClose, onTimeUpdate, onSpeedChange, onAudioReady }) {
    const audioRef = useRef(null);
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

    // Check audio status and generate if needed
    useEffect(() => {
        checkAndGenerateAudio();
    }, [novelSlug, chapterNumber]);

    // Update playback speed when settings change
    useEffect(() => {
        if (audioRef.current && settings?.ttsSpeed) {
            setSpeed(settings.ttsSpeed);
            audioRef.current.playbackRate = settings.ttsSpeed;
        }
    }, [settings?.ttsSpeed]);

    const checkAndGenerateAudio = async () => {
        setIsLoading(true);
        setError(null);

        try {
            // Check if audio exists
            const statusRes = await fetch(
                `${API_URL}/api/audio/status/${novelSlug}/${chapterNumber}`
            );
            const status = await statusRes.json();

            if (status.exists) {
                // Audio ready - load it
                const url = `${API_URL}/api/audio/stream/${novelSlug}/${chapterNumber}?t=${Date.now()}`;
                setAudioUrl(url);
                setAudioReady(true);
                setIsLoading(false);
                // Notify parent that audio is ready (for fetching timings)
                if (onAudioReady) {
                    // Add a small delay to ensure audio is loaded before fetching timings
                    setTimeout(() => onAudioReady(), 500);
                }
            } else if (status.generating) {
                // Already generating - poll for completion
                setGenerationStatus('Generating audio...');
                pollForCompletion();
            } else {
                // Need to generate
                setGenerationStatus('Starting TTS generation...');
                await generateAudio();
            }
        } catch (err) {
            console.error('Audio check error:', err);
            setError('Failed to check audio status');
            setIsLoading(false);
        }
    };

    const generateAudio = async () => {
        try {
            const voice = settings?.voice || 'af_heart';
            const res = await fetch(
                `${API_URL}/api/audio/generate/${novelSlug}/${chapterNumber}?voice=${voice}`,
                { method: 'POST' }
            );
            const data = await res.json();

            if (data.status === 'exists') {
                const url = `${API_URL}/api/audio/stream/${novelSlug}/${chapterNumber}?t=${Date.now()}`;
                setAudioUrl(url);
                setAudioReady(true);
                setIsLoading(false);
                if (onAudioReady) {
                    setTimeout(() => onAudioReady(), 500);
                }
            } else if (data.status === 'queued' || data.status === 'already_generating') {
                setGenerationStatus('Generating audio with Kokoro TTS...');
                pollForCompletion();
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

    const pollForCompletion = () => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(
                    `${API_URL}/api/audio/status/${novelSlug}/${chapterNumber}`
                );
                const status = await res.json();

                if (status.exists) {
                    clearInterval(interval);
                    const url = `${API_URL}/api/audio/stream/${novelSlug}/${chapterNumber}?t=${Date.now()}`;
                    setAudioUrl(url);
                    setAudioReady(true);
                    setIsLoading(false);
                    setGenerationStatus(null);
                    // Notify parent that audio is ready
                    if (onAudioReady) {
                        setTimeout(() => onAudioReady(), 500);
                    }
                } else if (status.error) {
                    clearInterval(interval);
                    setError(status.error);
                    setIsLoading(false);
                }
            } catch {
                clearInterval(interval);
                setError('Connection lost');
                setIsLoading(false);
            }
        }, 2000);

        // Timeout after 5 minutes
        setTimeout(() => clearInterval(interval), 300000);
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
            
            // Report time to parent for karaoke highlighting
            if (onTimeUpdate && dur && !isNaN(time)) {
                onTimeUpdate(time, audio.playbackRate);
            }
        };

        const handleLoadedMetadata = () => {
            setDuration(audio.duration);
            console.log('Audio loaded, duration:', audio.duration);
        };

        const handleEnded = () => {
            setIsPlaying(false);
            setProgress(0);
        };

        const handleCanPlay = () => {
            console.log('Audio can play');
        };

        audio.addEventListener('timeupdate', handleTimeUpdate);
        audio.addEventListener('loadedmetadata', handleLoadedMetadata);
        audio.addEventListener('ended', handleEnded);
        audio.addEventListener('canplay', handleCanPlay);

        return () => {
            audio.removeEventListener('timeupdate', handleTimeUpdate);
            audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
            audio.removeEventListener('ended', handleEnded);
            audio.removeEventListener('canplay', handleCanPlay);
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
        if (!seconds || isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    if (isMinimized) {
        return (
            <div className="audio-player-mini">
                <button className="mini-expand" onClick={() => setIsMinimized(false)}>
                    <ChevronUp size={16} />
                </button>
                <span className="mini-title">{chapterTitle || `Chapter ${chapterNumber}`}</span>
                <button
                    className="mini-play"
                    onClick={togglePlay}
                    disabled={!audioReady}
                >
                    {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                </button>
            </div>
        );
    }

    return (
        <div className="audio-player">
            {audioUrl && (
                <audio 
                    ref={audioRef} 
                    src={audioUrl} 
                    preload="auto"
                    crossOrigin="anonymous"
                />
            )}

            <div className="audio-player-header">
                <span className="audio-player-title">
                    {chapterTitle || `Chapter ${chapterNumber}`}
                </span>
                <div className="audio-player-actions">
                    <button className="btn-icon" onClick={() => setIsMinimized(true)}>
                        <ChevronDown size={16} />
                    </button>
                    <button className="btn-icon" onClick={onClose}>
                        <X size={16} />
                    </button>
                </div>
            </div>

            {isLoading ? (
                <div className="audio-player-loading">
                    <Loader size={24} className="spin" />
                    <span>{generationStatus || 'Loading audio...'}</span>
                </div>
            ) : error ? (
                <div className="audio-player-error">
                    <span>{error}</span>
                    <button className="btn btn-sm" onClick={checkAndGenerateAudio}>
                        Retry
                    </button>
                </div>
            ) : (
                <>
                    <div className="audio-progress" onClick={handleSeek}>
                        <div
                            className="audio-progress-bar"
                            style={{ width: `${progress}%` }}
                        />
                    </div>

                    <div className="audio-times">
                        <span>{formatTime(currentTime)}</span>
                        <span>{formatTime(duration)}</span>
                    </div>

                    <div className="audio-controls">
                        <button className="btn-icon" onClick={toggleMute}>
                            {isMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
                        </button>

                        <button
                            className="audio-play-btn"
                            onClick={togglePlay}
                            disabled={!audioReady}
                        >
                            {isPlaying ? <Pause size={24} /> : <Play size={24} />}
                        </button>

                        <button className="speed-btn" onClick={changeSpeed}>
                            {speed}x
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

export default AudioPlayer;