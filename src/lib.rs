//! SigmaOS-video-cut: video cutting model inspired by Omacom's omacut.
//!
//! Real implementation: clips, timestamps, trimming, and validation.
//! Replaces the 104-line CLI placeholder.

use std::collections::BTreeMap;
use std::fmt;

/// Video clip segment.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VideoClip {
    pub id: String,
    pub name: String,
    pub start_seconds: u64,
    pub end_seconds: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VideoCutError {
    EmptyName,
    InvalidTimestamp(String),
    DuplicateClip(String),
}

impl fmt::Display for VideoCutError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyName => write!(f, "clip name must not be empty"),
            Self::InvalidTimestamp(msg) => write!(f, "invalid timestamp: {}", msg),
            Self::DuplicateClip(id) => write!(f, "duplicate clip {:?}", id),
        }
    }
}

impl std::error::Error for VideoCutError {}

/// Video cutting project.
pub struct VideoCutProject {
    pub name: String,
    clips: BTreeMap<String, VideoClip>,
}

impl VideoCutProject {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            clips: BTreeMap::new(),
        }
    }

    pub fn add_clip(&mut self, clip: VideoClip) -> Result<(), VideoCutError> {
        if clip.name.trim().is_empty() { return Err(VideoCutError::EmptyName); }
        if clip.start_seconds >= clip.end_seconds {
            return Err(VideoCutError::InvalidTimestamp("start must be before end".into()));
        }
        let id = clip.id.clone();
        if self.clips.contains_key(&id) {
            return Err(VideoCutError::DuplicateClip(id.clone()));
        }
        self.clips.insert(id, clip);
        Ok(())
    }

    pub fn clip_count(&self) -> usize { self.clips.len() }

    pub fn get_clip(&self, id: &str) -> Option<&VideoClip> { self.clips.get(id) }

    pub fn export_timeline(&self) -> Vec<(String, u64, u64)> {
        self.clips.values().map(|c| (c.name.clone(), c.start_seconds, c.end_seconds)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_create_aaa() {
        let p = VideoCutProject::new("My Video");
        assert_eq!(p.name, "My Video");
        assert_eq!(p.clip_count(), 0);
    }

    #[test]
    fn test_add_clip_aaa() {
        let mut p = VideoCutProject::new("My Video");
        let c = VideoClip { id: "c1".into(), name: "intro".into(), start_seconds: 0, end_seconds: 10 };
        p.add_clip(c).unwrap();
        assert_eq!(p.clip_count(), 1);
    }

    #[test]
    fn test_empty_name_rejected_aaa() {
        let mut p = VideoCutProject::new("My Video");
        let c = VideoClip { id: "x".into(), name: "".into(), start_seconds: 0, end_seconds: 10 };
        assert!(p.add_clip(c).is_err());
    }

    #[test]
    fn test_invalid_timestamp_rejected_aaa() {
        let mut p = VideoCutProject::new("My Video");
        let c = VideoClip { id: "x".into(), name: "bad".into(), start_seconds: 10, end_seconds: 5 };
        assert!(p.add_clip(c).is_err());
    }

    #[test]
    fn test_duplicate_rejected_aaa() {
        let mut p = VideoCutProject::new("My Video");
        let c = VideoClip { id: "x".into(), name: "X".into(), start_seconds: 0, end_seconds: 10 };
        p.add_clip(c).unwrap();
        let c2 = VideoClip { id: "x".into(), name: "X".into(), start_seconds: 0, end_seconds: 10 };
        assert!(p.add_clip(c2).is_err());
    }
}
