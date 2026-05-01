import { useState, useEffect, useRef } from 'react';
import {
    useRoomContext,
    useLocalParticipant,
    useTracks,
    VideoTrack,
    RoomAudioRenderer,
} from '@livekit/components-react';
import { Track } from 'livekit-client';
import {
    Video,
    VideoOff,
    Mic,
    MicOff,
    Power,
    Cpu,
    HardDrive,
    Wifi,
    Activity,
    Minus,
    Square,
    X,
    Settings,
} from 'lucide-react';
import SettingsModal from './SettingsModal';

import AriesHood from './Hood';

import ErrorBoundary from './ErrorBoundary';
import { useKrispFilter } from '../hooks/useKrispFilter';
import './Interface.css';

function Interface({ onDisconnect, onSettings }) {
    const room = useRoomContext();
    const { localParticipant } = useLocalParticipant();

    const [currentTime, setCurrentTime] = useState(new Date());
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [systemInfo, setSystemInfo] = useState({
        cpu: { usage: 0, temp: 0 },
        memory: { usage: 0, total: 0 },
        gpu: { usage: 0, temp: 0 },
        network: { upload: 0, download: 0 },
    });
    const [chatMessages, setChatMessages] = useState([
        { type: 'system', text: 'Aries AI initialized...', timestamp: new Date() },
        { type: 'system', text: 'Connection connecting', timestamp: new Date() },
    ]);
    const [connectionStatus, setConnectionStatus] = useState('connecting');
    const [textInput, setTextInput] = useState('');
    const [isMaximized, setIsMaximized] = useState(false);
    const [scanResult, setScanResult] = useState(null);
    const [isScanning, setIsScanning] = useState(false);
    const [newsArticles, setNewsArticles] = useState([]);
    const [newsCategory, setNewsCategory] = useState('india');
    const [newsLoading, setNewsLoading] = useState(false);
    const [newsError, setNewsError] = useState('');
    const [isNewsPlaying, setIsNewsPlaying] = useState(false);
    const newsSpeechUtteranceRef = useRef(null);
    const transcriptRef = useRef(null);

    // Enable Krisp noise filter to remove background sounds (TV, etc.)
    const krispFilter = useKrispFilter();

    // Get video tracks
    const videoTracks = useTracks([Track.Source.Camera], {
        onlySubscribed: false,
    });

    // Get audio tracks for visualization
    const audioTracks = useTracks([Track.Source.Microphone], {
        onlySubscribed: false,
    });

    // Find agent's audio track (not local participant)
    const agentAudioTrack = audioTracks.find(
        t => t.participant.identity !== localParticipant?.identity
    )?.publication?.track;

    // Update time every second
    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // Simulate system info updates
    useEffect(() => {
        const interval = setInterval(() => {
            setSystemInfo({
                cpu: {
                    usage: Math.floor(Math.random() * 40 + 20),
                    temp: Math.floor(Math.random() * 20 + 45),
                },
                memory: {
                    usage: Math.floor(Math.random() * 30 + 40),
                    total: 16,
                },
                gpu: {
                    usage: Math.floor(Math.random() * 50 + 20),
                    temp: Math.floor(Math.random() * 25 + 50),
                },
                network: {
                    upload: (Math.random() * 10).toFixed(1),
                    download: (Math.random() * 50).toFixed(1),
                },
            });
        }, 2000);
        return () => clearInterval(interval);
    }, []);

    // Auto-scroll transcript to bottom when new messages arrive
    useEffect(() => {
        if (transcriptRef.current) {
            transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
        }
    }, [chatMessages]);

    // Monitor connection and speaking status
    useEffect(() => {
        if (!room) return;

        setConnectionStatus(room.state);

        room.on('connectionStateChanged', (state) => {
            setConnectionStatus(state);
            addChatMessage('system', `Connection ${state}`);
        });

        // Listen for agent speaking (track started)
        room.on('trackSubscribed', (track, publication, participant) => {
            if (track.kind === 'audio' && participant.identity !== localParticipant?.identity) {
                setIsSpeaking(true);
                setTimeout(() => setIsSpeaking(false), 2000);
            }
        });

        // Listen for data messages
        room.on('dataReceived', (payload, participant) => {
            try {
                const text = new TextDecoder().decode(payload);

                // Try to parse as JSON for structured commands
                try {
                    const message = JSON.parse(text);

                    // Handle PLAY_SONG command
                    if (message.type === 'PLAY_SONG') {
                        console.log(`[PLAY_SONG] Received: ${message.title} - ${message.url}`);
                        addChatMessage('system', `🎵 Playing: ${message.title}`);

                        // Play audio in Electron with video_id if available
                        playAudioFromUrl(message.url, message.title, message.video_id);
                        return;
                    }

                    // Handle NEWS_DATA command from backend
                    if (message.type === 'NEWS_DATA') {
                        console.log('[News] Received NEWS_DATA payload:', message);
                        setNewsLoading(false);
                        setNewsError('');
                        setNewsCategory(message.query || newsCategory);

                        if (Array.isArray(message.articles)) {
                            setNewsArticles(message.articles.slice(0, 10));
                        } else {
                            setNewsArticles([]);
                        }

                        addChatMessage('system', `📰 News updated for ${message.query || 'your selected category'}`);
                        return;
                    }

                    // Handle SCAN_RESULT command
                    if (message.type === 'SCAN_RESULT') {
                        console.log('[FileScan] Result received:', message);
                        setIsScanning(false);
                        setScanResult(message.result);

                        const result = JSON.parse(message.result);
                        const icon = result.status === 'clean' ? '✅' :
                            result.status === 'infected' ? '🚨' : '⚠️';

                        addChatMessage('Aries',
                            `${icon} Scan complete: ${result.file_name} - ${result.status.toUpperCase()}`
                        );

                        if (result.threat_name) {
                            addChatMessage('system', `⚠️ Threat: ${result.threat_name}`);
                        }

                        if (result.message) {
                            addChatMessage('system', result.message);
                        }
                        return;
                    }
                } catch (jsonError) {
                    // Not JSON, treat as plain text message
                    addChatMessage('Aries', text);
                }
            } catch (error) {
                console.error('[DataChannel] Error processing message:', error);
            }
        });

        // Register transcription handler for real-time speech-to-text
        // Wrap in try-catch to handle if already registered
        try {
            room.registerTextStreamHandler('lk.transcription', async (reader, participantInfo) => {
                try {
                    const message = await reader.readAll();
                    const isFinal = reader.info.attributes['lk.transcription_final'] === 'true';
                    const isTranscription = reader.info.attributes['lk.transcribed_track_id'];

                    // Show all transcriptions immediately for real-time display
                    if (message && message.trim()) {
                        // Determine if it's from agent or user
                        const isAgent = participantInfo.identity.toLowerCase().includes('agent') ||
                            participantInfo.identity.toLowerCase().includes('Aries');
                        const messageType = isAgent ? 'Aries' : 'user';

                        console.log(`📝 Transcription [${messageType}] ${isFinal ? 'FINAL' : 'INTERIM'}:`, message);

                        // Update or add message based on interim/final status
                        setChatMessages(prev => {
                            const lastMsg = prev[prev.length - 1];

                            if (isFinal) {
                                // If last message is interim from same speaker, replace it with final
                                if (lastMsg && lastMsg.type === messageType && !lastMsg.final) {
                                    return [...prev.slice(0, -1), {
                                        type: messageType,
                                        text: message,
                                        timestamp: new Date(),
                                        final: true
                                    }];
                                } else {
                                    // Add new final message
                                    return [...prev, {
                                        type: messageType,
                                        text: message,
                                        timestamp: new Date(),
                                        final: true
                                    }];
                                }
                            } else {
                                // Interim message
                                if (lastMsg && lastMsg.type === messageType && !lastMsg.final) {
                                    // Update existing interim message
                                    return [...prev.slice(0, -1), {
                                        ...lastMsg,
                                        text: message,
                                        timestamp: new Date()
                                    }];
                                } else {
                                    // Add new interim message
                                    return [...prev, {
                                        type: messageType,
                                        text: message,
                                        timestamp: new Date(),
                                        final: false
                                    }];
                                }
                            }
                        });
                    }
                } catch (error) {
                    console.error('Error reading transcription:', error);
                }
            });
        } catch (error) {
            // Handler already registered, ignore
            console.log('Transcription handler already registered');
        }
    }, [room, localParticipant]);

    // Show Krisp filter status in chat
    useEffect(() => {
        if (krispFilter.isEnabled) {
            addChatMessage('system', '🎤 Enhanced noise cancellation enabled - Background sounds filtered');
        } else if (!krispFilter.isSupported) {
            addChatMessage('system', '⚠️ Enhanced noise cancellation not supported on this browser');
        }
    }, [krispFilter.isEnabled, krispFilter.isSupported]);

    useEffect(() => {
        return () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
        };
    }, []);

    useEffect(() => {
        if (window.pythonAPI?.run) {
            fetchLatestNews(newsCategory);
        }
    }, []);

    const fetchLatestNews = async (categoryOverride) => {
        const category = categoryOverride || newsCategory;
        if (!window.pythonAPI || !window.pythonAPI.run) {
            setNewsError('News backend not available.');
            return;
        }

        setNewsLoading(true);
        setNewsError('');

        try {
            const responseText = await window.pythonAPI.run([
                'news_fetcher.py',
                '--category',
                category,
                '--count',
                '10'
            ]);

            const payload = JSON.parse(responseText.trim());
            if (payload.status !== 'ok') {
                throw new Error(payload.error || 'Unable to load news');
            }

            setNewsArticles(payload.articles || []);
            setNewsCategory(category);
            setNewsError('');
            addChatMessage('system', `📰 Loaded ${payload.articles?.length || 0} headlines for ${category}`);
        } catch (error) {
            console.error('[News] Fetch failed', error);
            setNewsArticles([]);
            setNewsError(error.message || 'Failed to fetch news headlines');
        } finally {
            setNewsLoading(false);
        }
    };

    const buildNewsSpeechText = (articles, category) => {
        if (!articles.length) {
            return `No headlines available for ${category}.`;
        }

        const lines = [`Here are the top ${articles.length} headlines for ${category}.`];
        for (let i = 0; i < articles.length; i += 1) {
            const article = articles[i];
            lines.push(`Headline ${i + 1}. ${article.title}. ${article.summary || 'No summary available.'}`);
        }
        return lines.join(' ');
    };

    const playNews = () => {
        if (!newsArticles.length) {
            setNewsError('Please fetch headlines first.');
            return;
        }

        if (!window.speechSynthesis) {
            setNewsError('Speech synthesis is not supported in this environment.');
            return;
        }

        if (isNewsPlaying) {
            window.speechSynthesis.cancel();
            setIsNewsPlaying(false);
            return;
        }

        const utterance = new SpeechSynthesisUtterance(buildNewsSpeechText(newsArticles.slice(0, 10), newsCategory));
        utterance.rate = 0.95;
        utterance.pitch = 1.0;
        utterance.volume = 0.95;

        const voices = window.speechSynthesis.getVoices();
        const voice = voices.find((v) => v.lang?.startsWith('en')) || voices[0];
        if (voice) utterance.voice = voice;

        utterance.onend = () => {
            setIsNewsPlaying(false);
            addChatMessage('system', '✅ News playback finished.');
        };
        utterance.onerror = (event) => {
            setIsNewsPlaying(false);
            setNewsError(event.error || 'News playback failed.');
        };

        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
        newsSpeechUtteranceRef.current = utterance;
        setIsNewsPlaying(true);
    };

    const addChatMessage = (type, text) => {
        setChatMessages(prev => [...prev, {
            type,
            text,
            timestamp: new Date()
        }].slice(-50)); // Keep last 50 messages
    };

    const formatTime = (date) => {
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    };

    const formatDate = (date) => {
        return date.toLocaleDateString('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        }).toUpperCase();
    };

    const handleMinimize = () => {
        if (window.windowAPI) {
            window.windowAPI.minimize();
        }
    };

    const handleMaximize = () => {
        if (window.windowAPI) {
            window.windowAPI.maximize();
            setIsMaximized(!isMaximized);
        }
    };

    const handleClose = () => {
        if (window.windowAPI) {
            window.windowAPI.close();
        } else {
            onDisconnect();
        }
    };

    const playAudioFromUrl = async (url, title, videoId = null) => {
        try {
            console.log(`🎵 [Audio] Attempting to play: ${url}`);
            console.log(`🎵 [Audio] Video ID: ${videoId}`);

            // For YouTube URLs, extract video ID and create direct watch URL
            if (url.includes('youtube.com') || url.includes('youtu.be')) {
                console.log('[Audio] YouTube detected');

                let finalUrl = url;

                // If we have a video ID, use it directly
                if (videoId) {
                    finalUrl = `https://www.youtube.com/watch?v=${videoId}&autoplay=1`;
                    console.log(`[Audio] Using direct video URL: ${finalUrl}`);
                } else {
                    // Try to extract video ID from URL
                    let extractedId = null;

                    // Check if it's a search results URL
                    if (url.includes('/results?search_query=')) {
                        console.log('[Audio] Search URL detected, cannot auto-play');
                        addChatMessage('system', `⚠️ Please click the first video to play: ${title}`);
                    } else {
                        // Try to extract from watch URL
                        const watchMatch = url.match(/[?&]v=([^&]+)/);
                        const shortMatch = url.match(/youtu\.be\/([^?&]+)/);

                        if (watchMatch) {
                            extractedId = watchMatch[1];
                        } else if (shortMatch) {
                            extractedId = shortMatch[1];
                        }

                        if (extractedId) {
                            finalUrl = `https://www.youtube.com/watch?v=${extractedId}&autoplay=1`;
                            console.log(`[Audio] Extracted video ID: ${extractedId}`);
                        }
                    }
                }

                // Open in external browser
                if (window.electronAPI && typeof window.electronAPI.openExternal === 'function') {
                    await window.electronAPI.openExternal(finalUrl);
                    addChatMessage('system', `🎵 Opened in browser: ${title}`);
                } else {
                    window.open(finalUrl, '_blank');
                    addChatMessage('system', `🎵 Opened in new tab: ${title}`);
                }
                return;
            }

            // For direct audio URLs (mp3, wav, etc.)
            const audio = new Audio(url);
            audio.volume = 0.7;

            audio.addEventListener('loadeddata', () => {
                console.log('[Audio] Loaded successfully');
                addChatMessage('system', `▶️ Playing: ${title}`);
            });

            audio.addEventListener('error', (e) => {
                console.error('[Audio] Playback error:', e);
                addChatMessage('system', `❌ Playback failed: ${title}`);
            });

            audio.addEventListener('ended', () => {
                console.log('[Audio] Playback finished');
                addChatMessage('system', `✅ Finished: ${title}`);
            });

            // Play with error handling
            audio.play().catch(err => {
                console.error('[Audio] Play failed:', err);
                // Fallback to opening in browser
                if (window.electronAPI && typeof window.electronAPI.openExternal === 'function') {
                    window.electronAPI.openExternal(url);
                } else {
                    window.open(url, '_blank');
                }
                addChatMessage('system', `🎵 Opened in browser: ${title}`);
            });

        } catch (error) {
            console.error('[Audio] Error:', error);
            addChatMessage('system', `❌ Audio error: ${error.message}`);
        }
    };

    const handleSendText = async () => {
        if (!textInput.trim() || !room) return;

        const message = textInput.trim();

        // Add to local chat
        addChatMessage('user', message);

        // Send via LiveKit data channel
        try {
            const encoder = new TextEncoder();
            const data = encoder.encode(message);
            await room.localParticipant.publishData(data, { reliable: true });
            console.log('Text message sent:', message);
        } catch (error) {
            console.error('Error sending text:', error);
            addChatMessage('system', 'Failed to send message');
        }

        setTextInput('');
    };

    const handleFileScan = async () => {
        if (!window.fileScanAPI || !room) {
            addChatMessage('system', '❌ File scanner not available');
            return;
        }

        try {
            // Open file picker
            const { filePath, canceled } = await window.fileScanAPI.selectFile();

            if (canceled || !filePath) {
                return;
            }

            const fileName = filePath.split('\\').pop();
            addChatMessage('user', `🔍 Scanning file: ${fileName}`);
            setIsScanning(true);
            setScanResult(null);

            // Send scan request to agent via data channel
            const encoder = new TextEncoder();
            const scanCommand = JSON.stringify({
                type: 'SCAN_FILE',
                filePath: filePath
            });
            await room.localParticipant.publishData(encoder.encode(scanCommand), { reliable: true });

            console.log('[FileScan] Request sent:', filePath);

        } catch (error) {
            console.error('[FileScan] Error:', error);
            addChatMessage('system', `❌ Scan error: ${error.message}`);
            setIsScanning(false);
        }
    };

    return (
        <div className="Aries-interface-v2">
            <RoomAudioRenderer />

            {/* Custom Title Bar */}
            <div className="title-bar">
                <div className="title-left">
                    <img src="./Aries.ico" alt="Aries" className="app-icon-small" />
                    <span className="app-title">Aries AI</span>
                    <span className="separator">|</span>
                    <span className="status-text">{connectionStatus}</span>
                </div>
                <div className="title-right">
                    <button className="title-btn" onClick={handleMinimize} title="Minimize">
                        <Minus size={16} />
                    </button>
                    <button className="title-btn" onClick={handleMaximize} title={isMaximized ? "Restore" : "Maximize"}>
                        <Square size={16} />
                    </button>
                    <button className="title-btn close" onClick={handleClose} title="Close">
                        <X size={16} />
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <div className="main-content">
                {/* Left Panel */}
                <div className="left-panel-v2">
                    {/* Video Feed */}
                    <div className="video-section">
                        <div className="section-header">
                            <Video size={16} />
                            <span>VISUAL INPUT</span>
                        </div>
                        <div className="video-box">
                            {videoTracks.length > 0 ? (
                                videoTracks.map((trackRef) => (
                                    <VideoTrack
                                        key={trackRef.publication.trackSid}
                                        trackRef={trackRef}
                                        className="video-stream"
                                    />
                                ))
                            ) : (
                                <div className="video-offline">
                                    <VideoOff size={40} />
                                    <span>VIDEO FEED OFFLINE</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* System Metrics */}
                    <div className="metrics-section">
                        <div className="section-header">
                            <Activity size={16} />
                            <span>SYSTEM METRICS</span>
                            <span className="status-online">● ONLINE</span>
                        </div>

                        <div className="metrics-grid">
                            {/* CPU */}
                            <div className="metric-card">
                                <div className="metric-icon cpu">
                                    <Cpu size={20} />
                                </div>
                                <div className="metric-data">
                                    <div className="metric-label">CPU LOAD</div>
                                    <div className="metric-value">{systemInfo.cpu.usage}%</div>
                                    <div className="metric-bar">
                                        <div
                                            className="metric-fill cpu"
                                            style={{ width: `${systemInfo.cpu.usage}%` }}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Memory */}
                            <div className="metric-card">
                                <div className="metric-icon memory">
                                    <HardDrive size={20} />
                                </div>
                                <div className="metric-data">
                                    <div className="metric-label">RAM USAGE</div>
                                    <div className="metric-value">{systemInfo.memory.usage}%</div>
                                    <div className="metric-bar">
                                        <div
                                            className="metric-fill memory"
                                            style={{ width: `${systemInfo.memory.usage}%` }}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* GPU */}
                            <div className="metric-card">
                                <div className="metric-icon gpu">
                                    <Activity size={20} />
                                </div>
                                <div className="metric-data">
                                    <div className="metric-label">GPU USAGE</div>
                                    <div className="metric-value">{systemInfo.gpu.usage}%</div>
                                    <div className="metric-bar">
                                        <div
                                            className="metric-fill gpu"
                                            style={{ width: `${systemInfo.gpu.usage}%` }}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Network */}
                            <div className="metric-card">
                                <div className="metric-icon network">
                                    <Wifi size={20} />
                                </div>
                                <div className="metric-data">
                                    <div className="metric-label">NETWORK</div>
                                    <div className="metric-stats">
                                        <span>↑ {systemInfo.network.upload} MB/s</span>
                                        <span>↓ {systemInfo.network.download} MB/s</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                    </div>

                    <div className="news-section">
                        <div className="section-header">
                            <span>NEWS BRIEFING</span>
                        </div>
                        <div className="news-controls">
                            <select
                                className="news-category-select"
                                value={newsCategory}
                                onChange={(e) => setNewsCategory(e.target.value)}
                            >
                                <option value="india">India</option>
                                <option value="world">World</option>
                                <option value="technology">Technology</option>
                                <option value="business">Business</option>
                                <option value="sports">Sports</option>
                                <option value="entertainment">Entertainment</option>
                            </select>
                            <button className="news-button" onClick={() => fetchLatestNews(newsCategory)} disabled={newsLoading}>
                                {newsLoading ? 'Loading...' : 'Refresh'}
                            </button>
                            <button className="news-button secondary" onClick={playNews} disabled={!newsArticles.length || newsLoading}>
                                {isNewsPlaying ? 'Stop' : 'Play News'}
                            </button>
                        </div>

                        {newsError && <div className="news-error">{newsError}</div>}

                        <div className="news-card-list">
                            {newsArticles.length === 0 && !newsLoading && (
                                <div className="news-empty">No news loaded yet. Click Refresh to begin.</div>
                            )}
                            {newsArticles.map((article, index) => (
                                <div key={`${article.url}-${index}`} className="news-card">
                                    <div className="news-card-header">
                                        <span className="news-card-rank">{index + 1}</span>
                                        <a href={article.url || '#'} target="_blank" rel="noreferrer" className="news-card-title">
                                            {article.title}
                                        </a>
                                    </div>
                                    <p className="news-card-summary">{article.summary || 'No summary available.'}</p>
                                    <div className="news-card-meta">
                                        <span>{article.source || 'News Feed'}</span>
                                        <span>{article.publishedAt ? new Date(article.publishedAt).toLocaleString() : ''}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                </div>

                <div className="center-panel">
                    <div className="orb-container" style={{ position: 'relative', width: '100%', height: '500px' }}>
                        <AriesHood audioTrack={agentAudioTrack} isSpeaking={isSpeaking} />
                    </div>



                    {/* Aries Identity Label - MOVED ABOVE BUTTONS */}
                    <div className={`Aries-identity-label ${isSpeaking ? 'speaking' : ''}`}>
                        A.R.I.E.S
                    </div>

                    {/* Controls - 4 Buttons in Box */}
                    <div className="controls-box">
                        <div className="center-controls">
                            <button
                                className="control-button mic"
                                onClick={() => {
                                    if (localParticipant) {
                                        localParticipant.setMicrophoneEnabled(!localParticipant.isMicrophoneEnabled);
                                    }
                                }}
                                title="Toggle Microphone"
                            >
                                {localParticipant?.isMicrophoneEnabled ? <Mic size={24} /> : <MicOff size={24} />}
                            </button>

                            <button
                                className="control-button end"
                                onClick={onDisconnect}
                                title="Disconnect"
                            >
                                <Power size={24} />
                            </button>

                            <button
                                className="control-button camera"
                                onClick={() => {
                                    if (localParticipant) {
                                        localParticipant.setCameraEnabled(!localParticipant.isCameraEnabled);
                                    }
                                }}
                                title="Toggle Camera"
                            >
                                {localParticipant?.isCameraEnabled ? <Video size={24} /> : <VideoOff size={24} />}
                            </button>

                            <button
                                className="control-button settings"
                                onClick={() => onSettings ? onSettings() : setShowSettings(true)}
                                title="Settings"
                            >
                                <Settings size={24} />
                            </button>

                            <button
                                className="control-button scan"
                                onClick={handleFileScan}
                                title="Scan File for Malware"
                                disabled={isScanning}
                            >
                                {isScanning ? '⏳' : '🛡️'}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Right Panel - Transcript */}
                <div className="right-panel-v2">
                    <div className="section-header">
                        <span>TRANSCRIPT</span>
                    </div>

                    {/* Date & Time Display */}
                    <div className="datetime-display">
                        <div className="date-box">
                            <span className="datetime-label">DATE</span>
                            <span className="datetime-value">{formatDate(currentTime)}</span>
                        </div>
                        <div className="time-box">
                            <span className="datetime-label">TIME</span>
                            <span className="datetime-value time-large">{formatTime(currentTime)}</span>
                        </div>
                    </div>

                    <div className="transcript-container" ref={transcriptRef}>
                        {chatMessages.map((msg, index) => (
                            <div key={index} className={`transcript-message ${msg.type}`}>
                                <div className="message-meta">
                                    <span className="message-sender">
                                        {msg.type === 'system' ? 'SYSTEM' : msg.type === 'Aries' ? 'Aries' : 'SPEAK'}
                                    </span>
                                    <span className="message-timestamp">
                                        {msg.timestamp.toLocaleTimeString()}
                                    </span>
                                </div>
                                <div className="message-content">{msg.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* Text Input */}
                    <div className="text-input-container">
                        <input
                            type="text"
                            className="text-input"
                            placeholder="Type a message..."
                            value={textInput}
                            onChange={(e) => setTextInput(e.target.value)}
                            onKeyPress={(e) => {
                                if (e.key === 'Enter' && textInput.trim()) {
                                    handleSendText();
                                }
                            }}
                        />
                        <button className="send-button" onClick={handleSendText}>
                            Send
                        </button>
                    </div>
                </div>
            </div>

            {/* Settings Modal */}
            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSave={(credentials) => {
                    // Settings saved, user may need to reconnect for changes to take effect
                    setShowSettings(false);
                }}
            />
        </div>
    );
}

export default Interface;
