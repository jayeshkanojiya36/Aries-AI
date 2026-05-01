import { useState, useEffect } from 'react';
import { LiveKitRoom } from '@livekit/components-react';
import Interface from './components/Interface';
import InterfaceDisconnected from './components/InterfaceDisconnected';
import SettingsModal from './components/SettingsModal';
import { generateLiveKitToken, getStoredCredentials, hasStoredCredentials } from './utils/tokenGenerator';
import './App.css';

function App() {
    const [token, setToken] = useState('');
    const [serverUrl, setServerUrl] = useState('');
    const [connected, setConnected] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);

    const handleConnect = async () => {
        setIsConnecting(true);

        const creds = getStoredCredentials();
        if (!creds) {
            setShowSettings(true);
            setIsConnecting(false);
            return;
        }

        const result = await generateLiveKitToken(
            creds.apiKey,
            creds.apiSecret,
            creds.serverUrl,
            creds.accessToken
        );

        if (result.success) {
            setToken(result.token);
            setServerUrl(result.serverUrl);
            setConnected(true);
        } else {
            alert('Failed to generate token. Please check your settings.');
            setShowSettings(true);
        }

        setIsConnecting(false);
    };

    const handleDisconnect = () => {
        setConnected(false);
        setToken('');
    };

    const handleSettingsSave = async (credentials) => {
        // Restart backend with new credentials if in Electron
        if (window.electronAPI && typeof window.electronAPI.startBackend === 'function') {
            try {
                console.log('Restarting backend with new credentials...');
                window.electronAPI.startBackend(credentials);
            } catch (e) {
                console.error('Failed to restart backend:', e);
            }
        }
        setShowSettings(false);
    };

    return (
        <div className="app">
            {connected ? (
                <LiveKitRoom
                    token={token}
                    serverUrl={serverUrl}
                    connect={true}
                    video={true}
                    audio={true}
                    onDisconnected={handleDisconnect}
                    className="livekit-room"
                    options={{
                        audioCaptureDefaults: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true,
                        },
                    }}
                >
                    <Interface
                        onDisconnect={handleDisconnect}
                        onSettings={() => setShowSettings(true)}
                    />
                </LiveKitRoom>
            ) : (
                <InterfaceDisconnected
                    onConnect={handleConnect}
                    onSettings={() => setShowSettings(true)}
                    isConnecting={isConnecting}
                />
            )}

            <SettingsModal
                isOpen={showSettings}
                onClose={() => setShowSettings(false)}
                onSave={handleSettingsSave}
            />
        </div>
    );
}

export default App;
