import { Composition, getInputProps } from 'remotion';
import { BouncySubs } from './BouncySubs';
import './index.css';

const inputProps = getInputProps() as any;
const durationInFrames = inputProps.totalFrames || 600;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="BouncySubs"
        component={BouncySubs}
        durationInFrames={durationInFrames}
        fps={60}
        width={1080}
        height={1920}
        defaultProps={{
          hasAvatar: inputProps.hasAvatar || false,
          avatarDuration: inputProps.avatarDuration || 0,
          videoDuration: inputProps.videoDuration || 10
        }}
      />
    </>
  );
};
