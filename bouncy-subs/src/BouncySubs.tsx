import React, { useEffect, useState } from 'react';
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { BouncyWord } from './BouncyWord';
import { parseSrtToWords, WordCue } from './parse-srt';

/* ─── Vignette Overlay ─── */
const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.85) 100%)',
      zIndex: 10,
      pointerEvents: 'none',
    }}
  />
);

/* ─── Impact Flash at the start of the video ─── */
const ImpactFlash: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flashDuration = Math.round(fps * 0.4); // 0.4 seconds

  const opacity = interpolate(frame, [0, flashDuration], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: `rgba(255, 255, 255, ${opacity})`,
        zIndex: 100,
        pointerEvents: 'none',
      }}
    />
  );
};

/* ─── Main Composition ─── */
export const BouncySubs: React.FC<{ videoDuration: number }> = ({ videoDuration }) => {
  const [words, setWords] = useState<WordCue[]>([]);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  useEffect(() => {
    fetch(staticFile('current_subs.srt'))
      .then((res) => {
        if (!res.ok) throw new Error("SRT not found");
        return res.text();
      })
      .then((text) => {
        const parsedWords = parseSrtToWords(text, fps);
        setWords(parsedWords);
      })
      .catch((err) => console.error('Failed to load SRT', err));
  }, [fps]);

  let activeCueIndex: number | null = null;
  const relativeFrame = frame; // No more avatar frames

  if (relativeFrame >= 0) {
    const cueGroups: Record<number, {start: number, end: number}> = {};
    words.forEach(w => {
      if (!cueGroups[w.cueIndex]) {
        cueGroups[w.cueIndex] = { start: w.startFrame, end: w.endFrame };
      } else {
        cueGroups[w.cueIndex].start = Math.min(cueGroups[w.cueIndex].start, w.startFrame);
        cueGroups[w.cueIndex].end = Math.max(cueGroups[w.cueIndex].end, w.endFrame);
      }
    });

    for (const [idx, bounds] of Object.entries(cueGroups)) {
      if (relativeFrame >= bounds.start && relativeFrame <= bounds.end) {
        activeCueIndex = parseInt(idx, 10);
        break;
      }
    }
  }

  const activeWords = activeCueIndex !== null 
    ? words.filter((w) => w.cueIndex === activeCueIndex) 
    : [];

  // Dynamic zoom-in transition for the first second to add motion
  const zoomDuration = fps * 1;
  const zoomScale = interpolate(frame, [0, zoomDuration], [1.15, 1.0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      
      {/* Dynamic Entrance Zoom */}
      <AbsoluteFill style={{ transform: `scale(${zoomScale})` }}>
        
        {/* Color Graded Main Video */}
        <OffthreadVideo
          src={staticFile('current_video.mp4')}
          volume={0.8}
          style={{ 
            width: '100%', 
            height: '100%', 
            objectFit: 'cover',
            // Premium Color Grading
            filter: 'saturate(1.35) contrast(1.15) brightness(1.05)' 
          }}
        />

      </AbsoluteFill>

      {/* Cinematic Effects */}
      <Vignette />
      <ImpactFlash />

      {/* Audio Layer */}
      <Audio src={staticFile('whoosh.wav')} volume={0.8} />
      <Audio src={staticFile('current_hook.mp3')} volume={1.0} />
      <Audio src={staticFile('current_bg.mp3')} volume={0.15} />

      {/* Subtitles Overlay */}
      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'center',
          top: '25%',
          flexDirection: 'row',
          flexWrap: 'wrap',
          alignContent: 'center',
          padding: '0 80px',
          zIndex: 50
        }}
      >
        {activeWords.map((wordObj, index) => (
          <BouncyWord
            key={`${wordObj.cueIndex}-${index}`}
            word={wordObj.word}
            startFrame={wordObj.startFrame}
            endFrame={wordObj.endFrame}
          />
        ))}
      </AbsoluteFill>
      
    </AbsoluteFill>
  );
};
