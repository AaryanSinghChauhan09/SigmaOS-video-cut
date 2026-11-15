use sigmaos_video_cut::{VideoCutProject, VideoClip};

#[test]
fn video_cut_project_works() {
    let mut p = VideoCutProject::new("Test Video");
    let c = VideoClip { id: "c1".into(), name: "intro".into(), start_seconds: 0, end_seconds: 10 };
    p.add_clip(c).unwrap();
    assert_eq!(p.clip_count(), 1);
    let timeline = p.export_timeline();
    assert_eq!(timeline.len(), 1);
    assert_eq!(timeline[0].0, "intro");
}
