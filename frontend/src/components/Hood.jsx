import React, { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';

import AriesOrb from './Orb';
import './Hood.css';

/**
 * AriesHood Component
 * 
 * Container for the "Identity" style interface (Circle + Text).
 * Fixed to ensure full visibility and locked 2D perspective.
 */
const AriesHood = ({ isSpeaking, audioTrack }) => {

    return (
        <div
            className="Aries-hood-container"
            style={{
                background: 'transparent',
                width: '100%',
                height: '100%',
                overflow: 'visible',
                position: 'relative'
            }}
        >
            <Canvas
                // Adjusted camera to Z=19 to fit the text at Y=4.5
                camera={{ position: [0, 0, 19], fov: 35 }}
                gl={{
                    alpha: true,
                    antialias: true,
                    powerPreference: "high-performance"
                }}
                dpr={[1, 2]}
            >
                <ambientLight intensity={1.0} />
                <pointLight position={[0, 0, 5]} intensity={2.0} color="#00eaff" />

                <Suspense fallback={null}>
                    <AriesOrb audioSource={audioTrack} />
                </Suspense>

                {/* STRICTLY DISABLE ROTATION so it stays flat 2D */}
                <OrbitControls
                    enableZoom={false}
                    enablePan={false}
                    enableRotate={false}
                />
            </Canvas>
        </div>
    );
};

export default AriesHood;
