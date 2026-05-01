import { useEffect, useState, useCallback } from 'react';
import { useLocalParticipant, useRoomContext } from '@livekit/components-react';
import { Track } from 'livekit-client';

/**
 * Custom hook to manage Krisp noise filtering for the local microphone
 * This filters out background noise like TV sounds before sending to the agent
 */
export function useKrispFilter() {
    const room = useRoomContext();
    const { localParticipant } = useLocalParticipant();
    const [isEnabled, setIsEnabled] = useState(false);
    const [isPending, setIsPending] = useState(false);
    const [isSupported, setIsSupported] = useState(true);
    const [krispProcessor, setKrispProcessor] = useState(null);

    // Check browser support and initialize Krisp
    useEffect(() => {
        let mounted = true;

        const initKrisp = async () => {
            try {
                // Dynamic import to only load when needed
                const { KrispNoiseFilter, isKrispNoiseFilterSupported } = await import('@livekit/krisp-noise-filter');

                if (!mounted) return;

                // Check if browser supports Krisp
                const supported = isKrispNoiseFilterSupported();
                setIsSupported(supported);

                if (!supported) {
                    console.warn('⚠️ Krisp noise filter is not supported on this browser');
                    return;
                }

                console.log('✅ Krisp noise filter is supported');
            } catch (error) {
                console.error('❌ Error loading Krisp:', error);
                setIsSupported(false);
            }
        };

        initKrisp();

        return () => {
            mounted = false;
        };
    }, []);

    // Apply Krisp filter to microphone track
    useEffect(() => {
        if (!room || !localParticipant || !isSupported) return;

        const applyKrispToMicrophone = async () => {
            try {
                // Find the microphone track
                const micPublication = localParticipant.getTrackPublication(Track.Source.Microphone);

                if (!micPublication || !micPublication.track) {
                    console.log('⏳ Waiting for microphone track...');
                    return;
                }

                const micTrack = micPublication.track;

                // Dynamic import
                const { KrispNoiseFilter } = await import('@livekit/krisp-noise-filter');

                // Create Krisp processor
                const processor = KrispNoiseFilter();
                setKrispProcessor(processor);

                console.log('🎤 Applying Krisp noise filter to microphone...');
                setIsPending(true);

                // Apply the processor to the microphone track
                await micTrack.setProcessor(processor);

                // Enable it by default
                await processor.setEnabled(true);
                setIsEnabled(true);
                setIsPending(false);

                console.log('✅ Krisp noise filter enabled successfully');
            } catch (error) {
                console.error('❌ Error applying Krisp filter:', error);
                setIsPending(false);
            }
        };

        // Listen for track published event
        const handleTrackPublished = (publication) => {
            if (publication.source === Track.Source.Microphone) {
                console.log('📢 Microphone track published, applying Krisp...');
                applyKrispToMicrophone();
            }
        };

        // Apply to existing track if available
        applyKrispToMicrophone();

        // Listen for new tracks
        localParticipant.on('trackPublished', handleTrackPublished);

        return () => {
            localParticipant.off('trackPublished', handleTrackPublished);
        };
    }, [room, localParticipant, isSupported]);

    // Toggle noise filter on/off
    const toggleNoiseFilter = useCallback(async () => {
        if (!krispProcessor || isPending) return;

        setIsPending(true);
        try {
            const newState = !isEnabled;
            await krispProcessor.setEnabled(newState);
            setIsEnabled(newState);
            console.log(`🔊 Krisp noise filter ${newState ? 'enabled' : 'disabled'}`);
        } catch (error) {
            console.error('❌ Error toggling Krisp:', error);
        } finally {
            setIsPending(false);
        }
    }, [krispProcessor, isEnabled, isPending]);

    return {
        isEnabled,
        isPending,
        isSupported,
        toggleNoiseFilter,
    };
}
