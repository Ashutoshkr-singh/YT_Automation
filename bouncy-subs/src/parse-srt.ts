export interface WordCue {
  word: string;
  startFrame: number;
  endFrame: number;
  cueIndex: number;
}

const timeToFrames = (timeStr: string, fps: number): number => {
  // timeStr: "HH:MM:SS,MMM"
  const [hms, ms] = timeStr.split(',');
  const [h, m, s] = hms.split(':').map(Number);
  const totalSeconds = h * 3600 + m * 60 + s + Number(ms) / 1000;
  return Math.round(totalSeconds * fps);
};

export const parseSrtToWords = (srtText: string, fps: number): WordCue[] => {
  const blocks = srtText.replace(/\r\n/g, '\n').split('\n\n').filter(b => b.trim().length > 0);
  const words: WordCue[] = [];
  let cueIndexCounter = 0;

  blocks.forEach(block => {
    const lines = block.split('\n');
    if (lines.length >= 3) {
      cueIndexCounter++;
      const timeLine = lines[1];
      const textLines = lines.slice(2).join(' ');
      
      const [startStr, endStr] = timeLine.split(' --> ');
      if (!startStr || !endStr) return;

      const cueStartFrame = timeToFrames(startStr.trim(), fps);
      const cueEndFrame = timeToFrames(endStr.trim(), fps);
      
      const cueWords = textLines.split(/\s+/).filter(w => w.trim().length > 0);
      if (cueWords.length === 0) return;
      
      const durationPerWord = (cueEndFrame - cueStartFrame) / cueWords.length;
      
      cueWords.forEach((word, index) => {
        words.push({
          word,
          startFrame: Math.round(cueStartFrame + index * durationPerWord),
          endFrame: Math.round(cueStartFrame + (index + 1) * durationPerWord),
          cueIndex: cueIndexCounter,
        });
      });
    }
  });

  return words;
};
