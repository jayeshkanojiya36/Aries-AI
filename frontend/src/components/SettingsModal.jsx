import { useState, useEffect } from 'react';
import { Settings, X, Save, Key, Server } from 'lucide-react';
import './SettingsModal.css';

function SettingsModal({ isOpen, onClose, onSave }) {
    const [apiKey, setApiKey] = useState('');
    const [apiSecret, setApiSecret] = useState('');
    const [serverUrl, setServerUrl] = useState('');
    const [accessToken, setAccessToken] = useState('');
    const [geminiKey, setGeminiKey] = useState('');
    const [newsApiKey, setNewsApiKey] = useState('');

    useEffect(() => {
        if (isOpen) {
            // Load saved credentials from localStorage
            const saved = localStorage.getItem('livekit_credentials');
            if (saved) {
                const creds = JSON.parse(saved);
                setApiKey(creds.apiKey || '');
                setApiSecret(creds.apiSecret || '');
                setServerUrl(creds.serverUrl || '');
                setAccessToken(creds.accessToken || '');
                setGeminiKey(creds.geminiKey || '');
                setNewsApiKey(creds.newsApiKey || '');
            }
        }
    }, [isOpen]);

    const handleSave = () => {
        const credentials = {
            apiKey: apiKey.trim(),
            apiSecret: apiSecret.trim(),
            serverUrl: serverUrl.trim(),
            accessToken: accessToken.trim(),
            geminiKey: geminiKey.trim(),
            newsApiKey: newsApiKey.trim()
        };

        // Save to localStorage
        localStorage.setItem('livekit_credentials', JSON.stringify(credentials));

        // Notify parent
        onSave(credentials);
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="settings-modal-overlay" onClick={onClose}>
            <div className="settings-modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="settings-modal-header">
                    <div className="settings-title">
                        <Settings size={24} />
                        <h2>LiveKit Settings</h2>
                    </div>
                    <button className="close-btn" onClick={onClose}>
                        <X size={20} />
                    </button>
                </div>

                <div className="settings-modal-body">
                    <p className="settings-description">
                        Configure your LiveKit credentials. These will be stored locally and used to auto-generate access tokens.
                    </p>

                    <div className="form-group">
                        <label htmlFor="apiKey">
                            <Key size={18} />
                            API Key
                        </label>
                        <input
                            type="text"
                            id="apiKey"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            placeholder="Enter your LiveKit API Key"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="apiSecret">
                            <Key size={18} />
                            API Secret
                        </label>
                        <input
                            type="password"
                            id="apiSecret"
                            value={apiSecret}
                            onChange={(e) => setApiSecret(e.target.value)}
                            placeholder="Enter your LiveKit API Secret"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="geminiKey">
                            <Key size={18} />
                            Gemini API Key
                        </label>
                        <input
                            type="password"
                            id="geminiKey"
                            value={geminiKey}
                            onChange={(e) => setGeminiKey(e.target.value)}
                            placeholder="Enter your Gemini API Key"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="newsApiKey">
                            <Key size={18} />
                            News API Key
                        </label>
                        <input
                            type="password"
                            id="newsApiKey"
                            value={newsApiKey}
                            onChange={(e) => setNewsApiKey(e.target.value)}
                            placeholder="Enter your News API Key"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="serverUrl">
                            <Server size={18} />
                            Server URL
                        </label>
                        <input
                            type="text"
                            id="serverUrl"
                            value={serverUrl}
                            onChange={(e) => setServerUrl(e.target.value)}
                            placeholder="wss://your-server.livekit.cloud"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="accessToken">
                            <Key size={18} />
                            Access Token (Optional)
                        </label>
                        <input
                            type="text"
                            id="accessToken"
                            value={accessToken}
                            onChange={(e) => setAccessToken(e.target.value)}
                            placeholder="Paste your generated token here"
                        />
                    </div>

                    <div className="settings-hint">
                        <p>💡 <strong>Where to find these:</strong></p>
                        <ul>
                            <li>Go to your LiveKit Cloud dashboard</li>
                            <li>Navigate to Settings → API Keys</li>
                            <li>Copy your API Key, Secret, and WebSocket URL</li>
                        </ul>
                    </div>
                </div>

                <div className="settings-modal-footer">
                    <button className="btn-cancel" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        className="btn-save"
                        onClick={handleSave}
                        disabled={!serverUrl.trim() || (!accessToken.trim() && (!apiKey.trim() || !apiSecret.trim()))}
                    >
                        <Save size={18} />
                        Save Settings
                    </button>
                </div>
            </div>
        </div>
    );
}

export default SettingsModal;
