const { contextBridge, ipcRenderer } = require('electron');

/**
 * Production-safe preload script
 * Strictly exposes whitelisted APIs only
 */

// ================================
// PYTHON BACKEND API
// ================================
contextBridge.exposeInMainWorld('pythonAPI', {
    /**
     * Run Python executable with arguments
     * @param {string[]} args
     * @returns {Promise<string>}
     */
    run: (args = []) => {
        if (!Array.isArray(args)) {
            throw new Error('pythonAPI.run expects an array of arguments');
        }
        return ipcRenderer.invoke('run-python', args);
    }
});

// ================================
// FILE SCANNER API
// ================================
contextBridge.exposeInMainWorld('fileScanAPI', {
    /**
     * Open file picker dialog for malware scanning
     * @returns {Promise<{filePath?: string, canceled: boolean}>}
     */
    selectFile: () => ipcRenderer.invoke('select-file-for-scan')
});

// ================================
// WINDOW CONTROLS API
// ================================
contextBridge.exposeInMainWorld('windowAPI', {
    minimize: () => ipcRenderer.send('minimize-window'),
    maximize: () => ipcRenderer.send('maximize-window'),
    close: () => ipcRenderer.send('close-window')
});

// ================================
// OPTIONAL: APP INFO (SAFE)
// ================================
contextBridge.exposeInMainWorld('appAPI', {
    platform: process.platform
});

contextBridge.exposeInMainWorld('electronAPI', {
    generateToken: (args) => ipcRenderer.invoke('generate-token', args),
    startBackend: (credentials) => ipcRenderer.send('start-backend', credentials),
    openExternal: (url) => ipcRenderer.invoke('open-external', url)
});
