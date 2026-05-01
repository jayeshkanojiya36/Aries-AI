import { useEffect, useRef, useCallback } from 'react';

/**
 * useVoiceAmplitude Hook
 * 
 * Analyzes audio amplitude from a MediaStream, Track, or HTMLAudioElement.
 * Designed for 60FPS animation loops - uses a ref for amplitude to avoid React render thrashing.
 * 
 * @param {MediaStream | MediaStreamTrack | HTMLAudioElement} audioSource - The source to analyze
 * @param {object} options - Configuration options
 * @param {number} options.fftSize - FFT size (default 512 for good time-domain resolution)
 * @param {number} options.smoothing - Smoothing time constant (0-1, default 0.8)
 * @returns {object} { amplitudeRef, getAmplitude } - Access current amplitude (0-1) via ref or getter
 */
export const useVoiceAmplitude = (audioSource, options = {}) => {
    const { fftSize = 512, smoothing = 0.8 } = options;

    // Use a ref for the amplitude to allow direct access in animation loops (useFrame)
    // without triggering React component re-renders.
    const amplitudeRef = useRef(0);

    const contextRef = useRef(null);
    const analyzerRef = useRef(null);
    const sourceRef = useRef(null);
    const dataArrayRef = useRef(null);
    const rafRef = useRef(null);

    // Cleanup function
    const cleanup = useCallback(() => {
        if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
        }
        if (sourceRef.current) {
            sourceRef.current.disconnect();
            sourceRef.current = null;
        }
        if (contextRef.current && contextRef.current.state !== 'closed') {
            contextRef.current.close();
            contextRef.current = null;
        }
        amplitudeRef.current = 0;
    }, []);

    useEffect(() => {
        if (!audioSource) return;

        const initAudio = async () => {
            try {
                // 1. Create AudioContext
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                const ctx = new AudioContext();
                contextRef.current = ctx;

                // 2. Create Analyzer
                const analyzer = ctx.createAnalyser();
                analyzer.fftSize = fftSize;
                analyzer.smoothingTimeConstant = smoothing;
                analyzerRef.current = analyzer;

                // 3. Create Source based on input type
                let sourceNode;

                if (audioSource instanceof HTMLAudioElement) {
                    // For HTMLAudioElement
                    // NOTE: We must connect to destination to ensure audio keeps playing
                    try {
                        sourceNode = ctx.createMediaElementSource(audioSource);
                        sourceNode.connect(analyzer);
                        analyzer.connect(ctx.destination);
                    } catch (e) {
                        // Fallback if media element source creation fails (e.g. CORS or already connected)
                        console.warn("useVoiceAmplitude: Could not create MediaElementSource, ensure CORS is handled.", e);
                        return;
                    }
                } else {
                    // For MediaStream or MediaStreamTrack (LiveKit Track)
                    let stream = audioSource;

                    // If it's a LiveKit Track or MediaStreamTrack, wrap in MediaStream
                    if (audioSource.kind === 'audio' || audioSource.mediaStreamTrack) {
                        const track = audioSource.mediaStreamTrack || audioSource;
                        stream = new MediaStream([track]);
                    } else if (audioSource instanceof MediaStream) {
                        stream = audioSource;
                    }

                    // Create stream source
                    // NOTE: We do NOT connect to destination to avoid echo/feedback mechanisms regarding the output
                    // as the original track is likely being played by a separate <audio> element (LiveKit RoomAudioRenderer)
                    sourceNode = ctx.createMediaStreamSource(stream);
                    sourceNode.connect(analyzer);
                }

                sourceRef.current = sourceNode;

                // 4. Setup Data Array
                const bufferLength = analyzer.frequencyBinCount;
                dataArrayRef.current = new Uint8Array(bufferLength);

                // 5. Resume Context Handler (Electron strict autoplay policy)
                const resumeContext = () => {
                    if (ctx.state === 'suspended') {
                        ctx.resume();
                    }
                };

                document.addEventListener('click', resumeContext, { once: true });
                document.addEventListener('keydown', resumeContext, { once: true });

                // Also try immediately
                resumeContext();

                // 6. Analysis Loop
                const analyze = () => {
                    if (!analyzerRef.current || !dataArrayRef.current) return;

                    // Get time domain data for waveform/amplitude analysis
                    analyzerRef.current.getByteTimeDomainData(dataArrayRef.current);

                    // Calculate RMS (Root Mean Square) for amplitude
                    let sum = 0;
                    for (let i = 0; i < bufferLength; i++) {
                        // Convert 0-255 to -1 to 1
                        const x = (dataArrayRef.current[i] - 128) / 128.0;
                        sum += x * x;
                    }

                    const rms = Math.sqrt(sum / bufferLength);

                    // Normalize and smooth logic could go here, but RMS is already 0-1.
                    // We can apply a gain factor if the signal is too quiet.
                    // For voice, typically we want to boost a bit.
                    const boosted = Math.min(rms * 4.0, 1.0); // Boost quiet voice

                    amplitudeRef.current = boosted;

                    rafRef.current = requestAnimationFrame(analyze);
                };

                analyze();

            } catch (err) {
                console.error("useVoiceAmplitude: Initialization failed", err);
            }
        };

        initAudio();

        return cleanup;
    }, [audioSource, fftSize, smoothing, cleanup]);

    return { amplitudeRef };
};
