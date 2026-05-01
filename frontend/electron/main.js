const { app, BrowserWindow, ipcMain, screen, dialog, shell } = require('electron');
const path = require('path');
const { spawn, execFile, execSync } = require('child_process');
const fs = require('fs');

// Setup logging
const logPath = path.join(app.getPath('userData'), 'backend.log');
const logStream = fs.createWriteStream(logPath, { flags: 'a' });

function logToFile(msg) {
    const timestamp = new Date().toISOString();
    const logMsg = `[${timestamp}] ${msg}\n`;
    logStream.write(logMsg);
    console.log(msg); // Also keep console for dev
}

let mainWindow = null;
let pythonProcess = null;
const skipBackendStart = process.env.SKIP_BACKEND_START === '1' || process.env.SKIP_BACKEND_START === 'true';

// ==================================================
// BACKEND LAUNCHER
// ==================================================
function getBackendLauncher() {
    const isDev = !app.isPackaged;

    if (isDev) {
        const scriptPath = path.join(__dirname, '..', '..', 'agent.py');
        const venvPython = path.join(__dirname, '..', '..', 'venv', 'Scripts', 'python.exe');
        if (fs.existsSync(scriptPath)) {
            let cmd = process.env.PYTHON_PATH || 'python';
            if (fs.existsSync(venvPython)) {
                cmd = venvPython;
            }
            return {
                command: cmd,
                args: [scriptPath, 'dev'],
                cwd: path.dirname(scriptPath)
            };
        }

        const exePath = path.join(__dirname, '..', 'backend', 'Aries.exe');
        if (fs.existsSync(exePath)) {
            return {
                command: exePath,
                args: ['start'],
                cwd: path.dirname(exePath)
            };
        }

        dialog.showErrorBox(
            'Critical Error',
            `Development backend not found:\n${scriptPath}\n\nOr missing executable:\n${exePath}`
        );
        app.quit();
    }

    const exePath = path.join(process.resourcesPath, 'backend', 'Aries.exe');
    if (!fs.existsSync(exePath)) {
        console.error('[Backend] agent.exe NOT FOUND:', exePath);
        dialog.showErrorBox(
            'Critical Error',
            `Backend executable missing:\n${exePath}\n\nPlease reinstall the application.`
        );
        app.quit();
    }

    return {
        command: exePath,
        args: ['start'],
        cwd: path.dirname(exePath)
    };
}

// ==================================================
// START PYTHON BACKEND
// ==================================================
const { AccessToken } = require('livekit-server-sdk');

// ... existing code ...

// ==================================================
// SYSTEM CONFIG
// ==================================================
let currentBackendEnv = {};

// ==================================================
// START PYTHON BACKEND
// ==================================================
function startPythonBackend(envOverride = {}) {
    // If running, stop it first
    stopPythonBackend();

    try {
        const backend = getBackendLauncher();

        // Merge process.env with any overrides (e.g. from Settings UI)
        const finalEnv = {
            ...process.env,
            ...currentBackendEnv,
            ...envOverride,
            PYTHONIOENCODING: 'utf-8',
            PYTHONUNBUFFERED: '1'
        };

        // Update current env storage
        currentBackendEnv = { ...currentBackendEnv, ...envOverride };

        logToFile(`[Backend] Launching with env vars: ${Object.keys(finalEnv).filter(k => k.includes('KEY') || k.includes('URL')).join(', ')}`);

        pythonProcess = spawn(backend.command, backend.args, {
            cwd: backend.cwd,
            windowsHide: true,
            detached: false,
            stdio: 'pipe',
            env: finalEnv
        });

        let stdoutBuffer = '';

        pythonProcess.stdout.on('data', data => {
            stdoutBuffer += data.toString();

            // Process complete lines only
            let lines = stdoutBuffer.split('\n');
            stdoutBuffer = lines.pop(); // Keep the last partial line in the buffer

            lines.forEach(line => {
                const str = line.trim();
                // Filter out HTTP noise and binary garbage to keep logs clean
                if (!str ||
                    str.startsWith('HTTP/1.1') ||
                    str.startsWith('Date:') ||
                    str.startsWith('Access-Control') ||
                    str.startsWith('Vary:') ||
                    str.startsWith('Etag:') ||
                    str.startsWith('Content-Type:') ||
                    str.length > 500 // Likely binary garbage
                ) return;

                logToFile(`[Backend Out] ${str}`);

                // Handle incoming JSON commands
                try {
                    if (str.startsWith('{') && str.endsWith('}')) {
                        const cmd = JSON.parse(str);
                        if (cmd.action === 'OPEN') {
                            handleOpenCommand(cmd.query);
                        }
                    }
                } catch (e) {
                    // Ignore parsing errors
                }
            });
        });

        pythonProcess.stderr.on('data', data => {
            logToFile(`[Backend Err] ${data.toString().trim()}`);
        });

        pythonProcess.on('close', code => {
            logToFile(`[Backend] Exited with code: ${code}`);
            pythonProcess = null;
        });

        pythonProcess.on('error', err => {
            logToFile(`[Backend] Launch failed: ${err.message}`);
        });

        logToFile(`[Backend] Started | PID: ${pythonProcess.pid}`);

    } catch (err) {
        logToFile(`[Backend] Failed to start: ${err.message}`);
        dialog.showErrorBox(
            'Backend Error',
            `Failed to start backend:\n${err.message}\nCheck logs at: ${logPath}`
        );
        app.quit();
    }
}

// ==================================================
// STOP PYTHON BACKEND
// ==================================================
function stopPythonBackend() {
    if (pythonProcess) {
        try {
            console.log('[Backend] Stopping process tree via taskkill...');
            if (process.platform === 'win32') {
                try {
                    // Force kill process tree
                    execSync(`taskkill /pid ${pythonProcess.pid} /T /F`);
                    console.log('[Backend] Process tree killed successfully');
                } catch (e) {
                    // Process might already be dead
                    console.log('[Backend] Taskkill warning (process might be dead):', e.message);
                }
            } else {
                pythonProcess.kill('SIGTERM');
            }
        } catch (err) {
            console.error('[Backend] Kill error:', err);
        }
        pythonProcess = null;
    }
}

// ==================================================
// HANDLE OPEN COMMAND
// ==================================================
function handleOpenCommand(query) {
    if (!query) return;

    logToFile(`[LinkHandler] Processing open request: ${query}`);

    // Check if it's a URL (http, https, or common domains)
    const isUrl = /^(http|https):\/\//i.test(query) ||
        /^www\./i.test(query) ||
        /\.(com|net|org|io|gov|edu)$/i.test(query);

    if (isUrl) {
        let url = query;
        if (!/^https?:\/\//i.test(url)) {
            url = 'https://' + url;
        }

        logToFile(`[LinkHandler] Opening URL: ${url}`);
        shell.openExternal(url).catch(err => {
            logToFile(`[LinkHandler] URL Error: ${err.message}`);
        });
    } else {
        // Assume it's a Windows app command
        logToFile(`[LinkHandler] Launching App: ${query}`);

        // Use 'start' to leverage Windows PATH and App Paths
        require('child_process').exec(`start "" "${query}"`, (err) => {
            if (err) {
                logToFile(`[LinkHandler] App Launch Error: ${err.message}`);
            } else {
                logToFile(`[LinkHandler] App launched successfully`);
            }
        });
    }
}

// ==================================================
// CREATE WINDOW (PRODUCTION)
// ==================================================
function createWindow() {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;

    mainWindow = new BrowserWindow({
        width: Math.min(width * 0.9, 1920),
        height: Math.min(height * 0.9, 1080),
        minWidth: 1200,
        minHeight: 700,
        center: true,
        frame: false,
        backgroundColor: '#0a0a0a',
        icon: path.join(process.resourcesPath, 'Aries.ico'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: true,
            // Enable audio/video playback
            autoplayPolicy: 'no-user-gesture-required',
            // Allow external media
            allowRunningInsecureContent: false
        }
    });

    // =========================
    // LOAD FRONTEND
    // =========================
    // =========================
    // LOAD FRONTEND
    // =========================
    // FORCE LOAD FROM BUILD (Fixes black screen / Dev Server garbage)
    const indexPath = path.join(__dirname, '../dist/index.html');
    console.log('[Electron] Loading:', indexPath);

    if (!fs.existsSync(indexPath)) {
        dialog.showErrorBox(
            'UI Error',
            `Frontend not found:\n${indexPath}\n\nPlease run "npm run build" first.`
        );
        app.quit();
        return;
    }

    // Load the local file
    mainWindow.loadFile(indexPath);

    // Open DevTools for debugging if needed
    // mainWindow.webContents.openDevTools();

    // Open external links in default browser instead of new Electron window
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        if (url.startsWith('http://') || url.startsWith('https://')) {
            shell.openExternal(url);
        }
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // 🔍 Debug load failures
    mainWindow.webContents.on('did-fail-load', (_, code, desc) => {
        console.error('FAILED TO LOAD:', code, desc);
    });
}

// ==================================================
// WINDOW CONTROLS IPC
// ==================================================
ipcMain.on('minimize-window', () => {
    mainWindow?.minimize();
});

ipcMain.on('maximize-window', () => {
    if (!mainWindow) return;
    mainWindow.isMaximized()
        ? mainWindow.restore()
        : mainWindow.maximize();
});

ipcMain.on('close-window', () => {
    mainWindow?.close();
});

// ==================================================
// SETTINGS & TOKEN IPC
// ==================================================
ipcMain.on('start-backend', (event, credentials) => {
    console.log('[IPC] Received request to restart backend with new credentials');

    const envVars = {
        LIVEKIT_URL: credentials.serverUrl,
        LIVEKIT_API_KEY: credentials.apiKey,
        LIVEKIT_API_SECRET: credentials.apiSecret,
        GEMINI_API_KEY: credentials.geminiKey,
        NEWS_API_KEY: credentials.newsApiKey
    };

    startPythonBackend(envVars);
});

ipcMain.handle('generate-token', async (_, args) => {
    const { apiKey, apiSecret, participantName, roomName } = args;

    if (!apiKey || !apiSecret) {
        throw new Error('Missing API Key or Secret');
    }

    try {
        const at = new AccessToken(apiKey, apiSecret, {
            identity: participantName,
            name: participantName,
        });

        at.addGrant({ roomJoin: true, room: roomName });

        const token = await at.toJwt();
        return { token };
    } catch (e) {
        console.error('[Token Error]', e);
        throw e;
    }
});

ipcMain.handle('open-external', async (_, url) => {
    try {
        await shell.openExternal(url);
        return { success: true };
    } catch (e) {
        console.error('[Open External] Error opening URL:', e);
        throw e;
    }
});

// ==================================================
// OPTIONAL PYTHON ONE-OFF CALLS
// ==================================================
ipcMain.handle('run-python', async (_, args) => {
    return new Promise((resolve, reject) => {
        let pythonCommand = process.env.PYTHON_PATH || 'python';
        const venvPython = path.join(__dirname, '..', '..', 'venv', 'Scripts', 'python.exe');
        if (fs.existsSync(venvPython)) {
            pythonCommand = venvPython;
        }
        const scriptArgs = args || [];
        const cwd = path.join(__dirname, '..', '..');

        execFile(pythonCommand, scriptArgs, { encoding: 'utf8', cwd }, (err, stdout, stderr) => {
            if (err) {
                reject(stderr || err.message);
            } else {
                resolve(stdout);
            }
        });
    });
});

// ==================================================
// FILE PICKER FOR MALWARE SCAN
// ==================================================
ipcMain.handle('select-file-for-scan', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        title: 'Select File to Scan for Malware',
        filters: [
            { name: 'All Files', extensions: ['*'] },
            { name: 'Executables', extensions: ['exe', 'dll', 'bat', 'cmd', 'ps1', 'msi'] },
            { name: 'Documents', extensions: ['pdf', 'docx', 'xlsx', 'pptx', 'zip', 'rar'] },
            { name: 'Scripts', extensions: ['js', 'py', 'vbs', 'jar'] }
        ]
    });

    if (result.canceled) {
        return { canceled: true };
    }

    return { filePath: result.filePaths[0] };
});

// ==================================================
// APP LIFECYCLE
// ==================================================
app.whenReady().then(() => {
    if (!skipBackendStart) {
        startPythonBackend();
    }

    // Give backend time to boot when launched automatically
    setTimeout(createWindow, 3000);
});

app.on('before-quit', stopPythonBackend);

app.on('window-all-closed', () => {
    stopPythonBackend();
    app.quit();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});
