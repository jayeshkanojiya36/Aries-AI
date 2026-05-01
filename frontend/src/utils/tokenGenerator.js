/**
 * Generate LiveKit Access Token via Backend API
 * This calls our FastAPI token server to generate tokens securely
 */

const TOKEN_SERVER_URL = 'http://localhost:8000';

export async function generateLiveKitToken(apiKey, apiSecret, serverUrl, accessToken) {
    const hasApiCreds = apiKey && apiSecret;
    const hasAccessToken = accessToken && accessToken.trim().length > 0;

    // Prefer API credentials when available, because saved access tokens may expire.
    if (!hasApiCreds && hasAccessToken) {
        return {
            success: true,
            token: accessToken,
            serverUrl: serverUrl
        };
    }

    if (!hasApiCreds) {
        return {
            success: false,
            error: 'Missing LiveKit API Key/Secret. Please open Settings and add credentials.'
        };
    }

    try {
        // Check if running in Electron and use IPC
        // We assume window.require is available in Electron via nodeIntegration (default false) or contextBridge
        // But since disconnected interface used it, we check:
        const electron = window.electronAPI || null;
        const canUseTokenIPC = electron && typeof electron.generateToken === 'function';

        if (canUseTokenIPC) {
            console.log('Generating token via IPC...');
            const result = await electron.generateToken({
                apiKey,
                apiSecret,
                serverUrl,
                roomName: 'vision-test-room',
                participantName: 'Aries User'
            });

            return {
                success: true,
                token: result.token,
                serverUrl: serverUrl
            };
        }

        // Fallback to fetch for web dev or non-Electron builds
        const response = await fetch(`${TOKEN_SERVER_URL}/generate-token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: apiKey,
                api_secret: apiSecret,
                server_url: serverUrl,
                room_name: 'vision-test-room',
                participant_name: 'Aries User'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate token');
        }

        const data = await response.json();

        return {
            success: true,
            token: data.token,
            serverUrl: data.server_url
        };
    } catch (error) {
        console.error('Error generating token:', error);
        return {
            success: false,
            error: error.message || 'Failed to generate token.'
        };
    }
}

export function getStoredCredentials() {
    try {
        const saved = localStorage.getItem('livekit_credentials');
        if (saved) {
            return JSON.parse(saved);
        }
    } catch (error) {
        console.error('Error loading credentials:', error);
    }
    return null;
}

export function hasStoredCredentials() {
    const creds = getStoredCredentials();
    return creds && creds.apiKey && creds.apiSecret && creds.serverUrl;
}
