import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

export const BouncyWord: React.FC<{
  word: string;
  startFrame: number;
  endFrame: number;
}> = ({ word, startFrame, endFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // The word is active while current frame is within its bounds
  const isActive = frame >= startFrame && frame <= endFrame;

  // Wait until startFrame to trigger the entrance spring
  const delay = startFrame;
  
  const springVal = spring({
    frame: frame - delay,
    fps,
    config: {
      mass: 0.5,
      damping: 12,
      stiffness: 200,
      overshootClamping: false,
    },
  });

  // Scale bounces from 0.5 to 1
  const scale = interpolate(springVal, [0, 1], [0.5, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Opacity fades in
  const opacity = interpolate(springVal, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // translateY bounces up from 20px to 0px
  const translateY = interpolate(springVal, [0, 1], [20, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <span
      style={{
        display: 'inline-block',
        transform: `scale(${scale}) translateY(${translateY}px)`,
        opacity,
        color: isActive ? '#FFE81F' : '#FFFFFF',
        textShadow: isActive
          ? '0px 0px 20px rgba(255, 232, 31, 0.6), 4px 4px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0px 10px 20px rgba(0,0,0,0.8)'
          : '4px 4px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0px 10px 20px rgba(0,0,0,0.8)',
        fontFamily: "'Montserrat', 'Inter', sans-serif",
        fontWeight: 900,
        fontSize: '78px',
        textTransform: 'uppercase',
        letterSpacing: '-2px',
        margin: '0 12px',
      }}
    >
      {word}
    </span>
  );
};
