import wave
import struct
import random
import math
import os

sample_rate = 44100
duration = 0.8
num_samples = int(sample_rate * duration)
amplitude = 32767

os.makedirs('bouncy-subs/public', exist_ok=True)
with wave.open('bouncy-subs/public/whoosh.wav', 'w') as wav_file:
    wav_file.setparams((1, 2, sample_rate, num_samples, 'NONE', 'not compressed'))
    for i in range(num_samples):
        progress = i / num_samples
        # Pink noise approximation
        noise = random.uniform(-1, 1)
        # Apply an impact envelope: fast attack, slow decay
        if progress < 0.05:
            envelope = progress / 0.05
        else:
            envelope = math.exp(-6 * (progress - 0.05))
        # Add a low-pass filter sweep effect by adding a sine wave that drops in frequency
        freq = 800 - (750 * progress)
        tone = math.sin(2 * math.pi * freq * (i / sample_rate))
        # Mix noise and tone
        sample = (noise * 0.7 + tone * 0.3) * envelope * amplitude
        wav_file.writeframes(struct.pack('h', int(sample)))
print('Whoosh generated successfully')
