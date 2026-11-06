mod media;
mod codec;

use media::MediaPlayer;
use codec::{Codec, CodecType};

fn main() {
    let _player = MediaPlayer::new();
    let _codec = Codec::new("h264".to_string(), CodecType::Video);
    println!("video-cut ready");
}
