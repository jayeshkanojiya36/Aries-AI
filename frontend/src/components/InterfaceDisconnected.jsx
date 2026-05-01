import { useState, useEffect, useRef } from 'react';
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
import './Interface.css';

// Import electron via preload bridge if available
const electron = window.electronAPI || null;

function JarvisInterfaceDisconnected({ onConnect, onSettings, isConnecting = false }) {
    const [currentTime, setCurrentTime] = useState(new Date());
    const [showSettings, setShowSettings] = useState(false);
    const [isMaximized, setIsMaximized] = useState(false);
    const [systemInfo, setSystemInfo] = useState({
        cpu: { usage: 0, temp: 0 },
        memory: { usage: 0, total: 0 },
        gpu: { usage: 0, temp: 0 },
        network: { upload: 0, download: 0 },
    });

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
                    usage: Math.floor(Math.random() * 30 + 30),
                    total: 16,
                },
                gpu: {
                    usage: Math.floor(Math.random() * 50 + 10),
                    temp: Math.floor(Math.random() * 25 + 50),
                },
                network: {
                    upload: (Math.random() * 5 + 1).toFixed(1),
                    download: (Math.random() * 15 + 5).toFixed(1),
                },
            });
        }, 2000);
        return () => clearInterval(interval);
    }, []);

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
        if (electron) {
            electron.ipcRenderer.send('minimize-window');
        }
    };

    const handleMaximize = () => {
        if (electron) {
            electron.ipcRenderer.send('maximize-window');
            setIsMaximized(!isMaximized);
        }
    };

    const handleClose = () => {
        if (electron) {
            electron.ipcRenderer.send('close-window');
        }
    };

    return (
        <div className="Aries-interface-v2">
            {/* Custom Title Bar */}
            <div className="title-bar">
                <div className="title-left">
                    <img src="./Aries.ico" alt="Aries" className="app-icon-small" />
                    <span className="app-title">Aries AI</span>
                    <span className="separator">|</span>
                    <span className="status-text">disconnected</span>
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
                {/* Left Panel - System Info */}
                <div className="left-panel-v2">
                    {/* Video Section */}
                    <div className="video-section">
                        <div className="section-header small">
                            <Video size={14} />
                            VISUAL INPUT
                        </div>
                        <div className="video-box">
                            <div className="video-offline">
                                <VideoOff size={48} />
                                <span>Camera Offline</span>
                            </div>
                        </div>
                    </div>

                    {/* System Metrics */}
                    <div className="metrics-section">
                        <div className="section-header small">
                            <Activity size={14} />
                            SYSTEM METRICS
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
                                        <div className="metric-fill cpu" style={{ width: `${systemInfo.cpu.usage}%` }}></div>
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
                                        <div className="metric-fill memory" style={{ width: `${systemInfo.memory.usage}%` }}></div>
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
                                        <div className="metric-fill gpu" style={{ width: `${systemInfo.gpu.usage}%` }}></div>
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
                </div>

                {/* Center Panel - AI Orb */}
                <div className="center-panel">
                    <div className="orb-container" style={{ position: 'relative', width: '100%', height: '500px' }}>
                        <AriesHood audioTrack={null} isSpeaking={false} />
                    </div>



                    {/* Controls - 4 Buttons in Box */}
                    <div className="controls-box">
                        <div className="center-controls">
                            <button
                                className="control-button mic"
                                disabled={true}
                                title="Microphone (Disabled)"
                            >
                                <MicOff size={24} />
                            </button>

                            <button
                                className="control-button connect"
                                onClick={onConnect}
                                title={isConnecting ? "Connecting..." : "Connect"}
                                disabled={isConnecting}
                            >
                                <Power size={24} />
                            </button>

                            <button
                                className="control-button camera"
                                disabled={true}
                                title="Camera (Disabled)"
                            >
                                <VideoOff size={24} />
                            </button>

                            <button
                                className="control-button settings"
                                onClick={() => onSettings ? onSettings() : setShowSettings(true)}
                                title="Settings"
                            >
                                <Settings size={24} />
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

                    <div className="transcript-container">
                        <div className="transcript-message system">
                            <div className="message-meta">
                                <span className="message-sender">SYSTEM</span>
                                <span className="message-timestamp">{currentTime.toLocaleTimeString()}</span>
                            </div>
                            <div className="message-content">Aries AI initialized...</div>
                        </div>
                        <div className="transcript-message system">
                            <div className="message-meta">
                                <span className="message-sender">SYSTEM</span>
                                <span className="message-timestamp">{currentTime.toLocaleTimeString()}</span>
                            </div>
                            <div className="message-content">Disconnected. Click Connect to start.</div>
                        </div>
                    </div>

                    {/* Text Input - Disabled */}
                    <div className="text-input-container">
                        <input
                            type="text"
                            className="text-input"
                            placeholder="Connect to send messages..."
                            disabled={true}
                        />
                        <button className="send-button" disabled={true}>
                            Send
                        </button>
                    </div>
                </div>
            </div>

            {/* Settings Modal */}
            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSave={() => setShowSettings(false)}
            />
        </div>
    );
}

export default JarvisInterfaceDisconnected;
