import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useVoiceAmplitude } from '../hooks/useVoiceAmplitude';

/**
 * AriesOrb Component
 * 
 * A futuristic, cinematic AI core that reacts to voice amplitude.
 * Performance optimized using GLSL shaders for particle movement.
 * 
 * @param {MediaStreamTrack | MediaStream | HTMLAudioElement} audioSource - Audio source for reaction
 * @param {number} particleCount - Number of particles (default: 8000)
 * @param {number} radius - Base radius of the orb (default: 2.5)
 */
const AriesOrb = ({ audioSource, particleCount = 8000, radius = 2.5 }) => {
    const meshRef = useRef();
    const materialRef = useRef();

    // Get amplitude from audio source using our custom hook
    // normalize: returns a ref for performance (no re-renders)
    const { amplitudeRef } = useVoiceAmplitude(audioSource, {
        fftSize: 512,
        smoothing: 0.6 // Slightly snappier for voice
    });

    // --- Geometry Generation (One-time CPU cost) ---
    const { positions, colors, randoms } = useMemo(() => {
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);
        const randoms = new Float32Array(particleCount);

        const color1 = new THREE.Color("#db2781"); // Requested Red/Pink
        const color2 = new THREE.Color("#ffaa00"); // Vibrant Orange/Gold

        for (let i = 0; i < particleCount; i++) {
            // Spherical distribution
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos((Math.random() * 2) - 1);

            // Add slight randomness to radius for depth
            const r = radius * (0.95 + Math.random() * 0.1);

            const x = r * Math.sin(phi) * Math.cos(theta);
            const y = r * Math.sin(phi) * Math.sin(theta);
            const z = r * Math.cos(phi);

            positions[i * 3] = x;
            positions[i * 3 + 1] = y;
            positions[i * 3 + 2] = z;

            // Color gradient mixing
            const mixRatio = Math.random();
            const mixedColor = color1.clone().lerp(color2, mixRatio);

            colors[i * 3] = mixedColor.r;
            colors[i * 3 + 1] = mixedColor.g;
            colors[i * 3 + 2] = mixedColor.b;

            // Random attributes for shader animation offset
            randoms[i] = Math.random();
        }

        return { positions, colors, randoms };
    }, [particleCount, radius]);

    // --- Shader Definitions ---

    const vertexShader = `
        uniform float uTime;
        uniform float uAmplitude;
        
        attribute float aRandom;
        attribute vec3 customColor;
        
        varying vec3 vColor;
        varying float vDistance;
        
        // Simplex noise function (simplified)
        // ... (omitted for brevity, using simple sin/cos combination for performance)
        
        void main() {
            vColor = customColor;
            
            vec3 pos = position;
            
            // 1. Idle Breathing
            // Particles move in/out slightly based on time and their random offset
            float breath = sin(uTime * 1.0 + aRandom * 6.0) * 0.05;
            
            // 2. Voice Reaction (Expansion)
            // Push particles outward based on amplitude
            // Non-linear expansion creates a "core" that stays and "outer shell" that flares
            float reaction = uAmplitude * 1.0; 
            
            // Add some noise/turbulence to the expansion reaction
            float turbulence = sin(pos.y * 5.0 + uTime * 5.0) * cos(pos.x * 5.0) * uAmplitude * 0.2;
            
            // Combine shifts
            vec3 normal = normalize(pos);
            vec3 targetPos = pos + normal * (breath + reaction + turbulence);
            
            // 3. Rotation/Swirl effect (handled in JS for whole mesh, or here for individual particles if needed)
            
            vec4 mvPosition = modelViewMatrix * vec4(targetPos, 1.0);
            
            // Dynamic Point Size
            // Larger when closer to camera, larger when loud
            gl_PointSize = (3.0 + uAmplitude * 5.0) * (30.0 / -mvPosition.z);
            
            gl_Position = projectionMatrix * mvPosition;
            
            // Pass distance to fragment for fading
            vDistance = -mvPosition.z;
        }
    `;

    const fragmentShader = `
        varying vec3 vColor;
        
        void main() {
            // Circular particle
            vec2 uv = gl_PointCoord - 0.5;
            float r = length(uv);
            if (r > 0.5) discard;
            
            // Glow gradient: center is bright, edge is soft
            float glow = 1.0 - (r * 2.0); // 0 at edge, 1 at center
            glow = pow(glow, 2.0); // make it tighter
            
            // Final color
            gl_FragColor = vec4(vColor, glow);
        }
    `;

    // Uniforms
    const uniforms = useMemo(() => ({
        uTime: { value: 0 },
        uAmplitude: { value: 0 }
    }), []);

    // --- Animation Loop ---
    useFrame((state) => {
        const { clock } = state;
        const time = clock.getElapsedTime();

        // Update amplitude uniform with smooth lerp for "Damped/Spring-like" motion
        // We do the smoothing here in JS before sending to shader for better control
        if (materialRef.current) {
            materialRef.current.uniforms.uTime.value = time;

            const targetAmp = amplitudeRef.current || 0;
            const currentAmp = materialRef.current.uniforms.uAmplitude.value;

            // Lerp factor: 0.1 gives a smooth delay. 
            // If target > current (attack), move fast. If target < current (decay), move slow.
            const lerpFactor = targetAmp > currentAmp ? 0.3 : 0.05;

            materialRef.current.uniforms.uAmplitude.value += (targetAmp - currentAmp) * lerpFactor;
        }

        // Slowly rotate the entire orb for "Alive" feel
        if (meshRef.current) {
            meshRef.current.rotation.y = time * 0.05;
            meshRef.current.rotation.z = Math.sin(time * 0.1) * 0.02;
        }
    });

    return (
        <points ref={meshRef}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    count={positions.length / 3}
                    array={positions}
                    itemSize={3}
                />
                <bufferAttribute
                    attach="attributes-customColor"
                    count={colors.length / 3}
                    array={colors}
                    itemSize={3}
                />
                <bufferAttribute
                    attach="attributes-aRandom"
                    count={randoms.length}
                    array={randoms}
                    itemSize={1}
                />
            </bufferGeometry>
            <shaderMaterial
                ref={materialRef}
                vertexShader={vertexShader}
                fragmentShader={fragmentShader}
                uniforms={uniforms}
                transparent={true}
                depthWrite={false}
                blending={THREE.AdditiveBlending}
            />
        </points>
    );
};

export default AriesOrb;
