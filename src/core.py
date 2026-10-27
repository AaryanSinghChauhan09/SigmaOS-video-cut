"""Lossless-ish video trimmer planner for SigmaOS-video-cut (omacut-style).

The engine plans ffmpeg trims: probe metadata parsing, range validation
(rejecting out-of-bounds cuts), ffmpeg cut argv and concat-demuxer playlists.
Running ffmpeg is the thin execute layer -- self_test() only exercises the
pure probe/parse/plan layer (no subprocess, no media files needed).
Principles: Separation of Concerns, Defensive Programming, Fail-Fast, KISS.
"""
import argparse, json, os, shlex, sys

ENGINE = {
    "name": "sigma-cut",
    "summary": "Plan video trims and concatenation with range validation",
    "language": "python",
    "verbs": ["probe-plan", "cut-plan", "validate-range", "concatenate-plan"],
    "principles": ["Separation of Concerns", "Defensive Programming",
                   "Fail-Fast", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-cut probe-plan talk.mp4
ffprobe -v error -print_format json -show_format -show_streams talk.mp4
$ sigma-cut validate-range --start 10 --end 60 --duration 612.34
ok: 50.000s window (10.000s .. 60.000s of 612.34s)
$ sigma-cut cut-plan talk.mp4 --start 10 --end 60 --out part.mp4
ffmpeg -hide_banner -loglevel error -y -ss 10.000 -i talk.mp4 -t 50.000 -c copy part.mp4
$ sigma-cut concatenate-plan a.mp4 b.mp4 --out movie.mp4
"""


class VideoCutError(Exception):
    pass


PROBE_ARGV = ["ffprobe", "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams"]


# --------------------------------------------------------------------------- #
#  PURE probe / parse / plan layer
# --------------------------------------------------------------------------- #
def probe_plan(path):
    """Build the ffprobe argv for a media file (pure string building)."""
    if not path or not isinstance(path, str):
        raise VideoCutError("no input file given")
    return PROBE_ARGV + [path]


def parse_probe(text):
    """Parse an ffprobe -show_format -show_streams JSON dump."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise VideoCutError(f"probe output is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise VideoCutError("probe output must be a JSON object")
    fmt = data.get("format", {})
    if not isinstance(fmt, dict):
        raise VideoCutError("probe output has no format section")
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        raise VideoCutError("probe output has no usable duration")
    if duration <= 0:
        raise VideoCutError("probe duration must be > 0")
    streams = data.get("streams", [])
    if not isinstance(streams, list):
        raise VideoCutError("probe streams section is malformed")
    return {
        "duration": duration,
        "video": any(s.get("codec_type") == "video" for s in streams),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "format_name": fmt.get("format_name", ""),
        "nb_streams": len(streams),
    }


def validate_range(start, end, duration):
    """Validate a [start, end) cut window against the media duration."""
    try:
        start, end, duration = float(start), float(end), float(duration)
    except (TypeError, ValueError):
        raise VideoCutError("start/end/duration must be numbers")
    if duration <= 0:
        raise VideoCutError("duration must be > 0")
    if start < 0:
        raise VideoCutError(f"start {start:g}s must be >= 0")
    if end <= start:
        raise VideoCutError(f"end {end:g}s must be after start {start:g}s")
    if end > duration + 1e-6:
        raise VideoCutError(f"end {end:g}s is beyond duration {duration:g}s")
    return {"start": start, "end": end, "duration": duration,
            "length": round(end - start, 3)}


def cut_plan(src, start, end, out, duration=None, reencode=False, crf=18):
    """Build the ffmpeg argv trimming [start, end) out of `src`."""
    if not src or not out:
        raise VideoCutError("cut needs an input and an output path")
    if duration is not None:
        validate_range(start, end, duration)
    else:
        try:
            if float(end) <= float(start):
                raise VideoCutError("end must be after start")
        except (TypeError, ValueError):
            raise VideoCutError("start/end must be numbers")
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{float(start):.3f}",
            "-i", src, "-t", f"{float(end) - float(start):.3f}"]
    if reencode:
        try:
            crf = int(crf)
        except (TypeError, ValueError):
            raise VideoCutError("crf must be an integer")
        if not (0 <= crf <= 51):
            raise VideoCutError("crf must be 0..51")
        argv += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                 "-c:a", "aac"]
    else:
        argv += ["-c", "copy"]
    argv.append(out)
    return argv


def render_concat_list(files):
    """Render an ffmpeg concat-demuxer list file body."""
    if len(files) < 2:
        raise VideoCutError("concatenate needs at least two inputs")
    lines = []
    for f in files:
        if not f or not isinstance(f, str):
            raise VideoCutError(f"bad input entry: {f!r}")
        lines.append("file '" + f.replace("'", r"'\''") + "'")
    return "\n".join(lines) + "\n"


def concatenate_plan(files, out, mode="demuxer", list_path="concat.txt"):
    """Plan a stream-copy concatenation of `files` into `out`."""
    if not out:
        raise VideoCutError("no output path given")
    if mode not in ("demuxer", "protocol"):
        raise VideoCutError(f"unknown concat mode: {mode!r}")
    if mode == "demuxer":
        body = render_concat_list(files)
        argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", out]
        return {"argv": argv, "list_path": list_path, "list_body": body}
    joined = "|".join(files)
    if len(files) < 2:
        raise VideoCutError("concatenate needs at least two inputs")
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", f"concat:{joined}", "-c", "copy", out]
    return {"argv": argv, "list_path": None, "list_body": None}


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("probe-plan", help="build an ffprobe invocation")
    pb.add_argument("file")
    cp = sub.add_parser("cut-plan", help="build an ffmpeg trim invocation")
    cp.add_argument("file")
    cp.add_argument("--start", type=float, required=True)
    cp.add_argument("--end", type=float, required=True)
    cp.add_argument("--out", required=True)
    cp.add_argument("--duration", type=float, default=None)
    cp.add_argument("--reencode", action="store_true")
    cp.add_argument("--crf", type=int, default=18)
    vr = sub.add_parser("validate-range", help="validate a cut window")
    vr.add_argument("--start", type=float, required=True)
    vr.add_argument("--end", type=float, required=True)
    vr.add_argument("--duration", type=float, required=True)
    cc = sub.add_parser("concatenate-plan", help="plan a stream-copy concat")
    cc.add_argument("file", nargs="+")
    cc.add_argument("--out", required=True)
    cc.add_argument("--mode", default="demuxer", choices=["demuxer", "protocol"])
    cc.add_argument("--list-path", default="concat.txt")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "probe-plan":
            print(" ".join(shlex.quote(a) for a in probe_plan(args.file)))
        elif args.cmd == "cut-plan":
            plan = cut_plan(args.file, args.start, args.end, args.out,
                            args.duration, args.reencode, args.crf)
            print(" ".join(shlex.quote(a) for a in plan))
        elif args.cmd == "validate-range":
            r = validate_range(args.start, args.end, args.duration)
            print(f'ok: {r["length"]:g}s window '
                  f'({r["start"]:g}s .. {r["end"]:g}s of {r["duration"]:g}s)')
        elif args.cmd == "concatenate-plan":
            plan = concatenate_plan(args.file, args.out, args.mode, args.list_path)
            print(" ".join(shlex.quote(a) for a in plan["argv"]))
            if plan["list_body"]:
                print(plan["list_body"], end="", file=sys.stderr)
        return 0
    except (VideoCutError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
#  Tests (pure probe/parse/plan layer only -- no subprocess)
# --------------------------------------------------------------------------- #
SAMPLE_PROBE = """{
    "streams": [
        {"index": 0, "codec_name": "h264", "codec_type": "video",
         "width": 1920, "height": 1080},
        {"index": 1, "codec_name": "aac", "codec_type": "audio",
         "channels": 2}
    ],
    "format": {
        "filename": "talk.mp4",
        "nb_streams": 2,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "612.340000",
        "size": "524288000"
    }
}
"""


def self_test() -> None:
    argv = probe_plan("talk.mp4")
    assert argv[:6] == ["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_format"], argv
    assert argv[-1] == "talk.mp4" and "-show_streams" in argv
    try:
        probe_plan("")
    except VideoCutError:
        pass
    else:
        raise AssertionError("empty probe input not rejected")

    info = parse_probe(SAMPLE_PROBE)
    assert info["duration"] == 612.34
    assert info["video"] is True and info["audio"] is True
    assert info["nb_streams"] == 2
    audio_only = '{"streams": [{"codec_type": "audio"}], ' \
                 '"format": {"duration": "12.5"}}'
    a = parse_probe(audio_only)
    assert a["video"] is False and a["audio"] is True and a["duration"] == 12.5
    for bad in ("", "not json", "[1, 2]", "{}",
                '{"format": {"duration": "0"}}',
                '{"streams": [], "format": {}}'):
        try:
            parse_probe(bad)
        except VideoCutError:
            pass
        else:
            raise AssertionError(f"bad probe output not accepted: {bad!r}")

    r = validate_range(10, 30, 612.34)
    assert r["length"] == 20.0 and r["start"] == 10.0, r
    for bad in ((-1, 10, 100), (30, 10, 100), (0, 200, 100), (0, 0, 100),
                (0, 10, 0), ("a", 10, 100)):
        try:
            validate_range(*bad)
        except VideoCutError:
            pass
        else:
            raise AssertionError(f"out-of-bounds range not rejected: {bad!r}")

    argv = cut_plan("talk.mp4", 10, 60, "part.mp4", duration=612.34)
    assert argv[:8] == ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", "10.000", "-i"], argv
    assert argv[argv.index("-t") + 1] == "50.000"
    assert argv[-3:] == ["-c", "copy", "part.mp4"]
    re = cut_plan("talk.mp4", 0, 5, "x.mp4", reencode=True)
    assert "libx264" in re and re[re.index("-crf") + 1] == "18"
    # out-of-bounds end is rejected when a duration is known
    try:
        cut_plan("talk.mp4", 10, 9999, "part.mp4", duration=612.34)
    except VideoCutError:
        pass
    else:
        raise AssertionError("out-of-bounds cut not rejected")
    try:
        cut_plan("talk.mp4", 10, 5, "part.mp4")
    except VideoCutError:
        pass
    else:
        raise AssertionError("reversed cut not rejected")
    try:
        cut_plan("talk.mp4", 0, 5, "x.mp4", reencode=True, crf=99)
    except VideoCutError:
        pass
    else:
        raise AssertionError("bad crf not rejected")

    plan = concatenate_plan(["a.mp4", "b.mp4", "c.mp4"], "movie.mp4")
    body = plan["list_body"]
    assert body == "file 'a.mp4'\nfile 'b.mp4'\nfile 'c.mp4'\n", body
    argv = plan["argv"]
    assert argv[argv.index("-f") + 1] == "concat"
    assert argv[argv.index("-i") + 1] == "concat.txt"
    assert argv[-1] == "movie.mp4" and "copy" in argv
    # single-quote escaping in file names (concat list injection defence)
    tricky = render_concat_list(["it's.mp4", "b.mp4"])
    assert r"it'\''s.mp4" in tricky, tricky
    proto = concatenate_plan(["a.mp4", "b.mp4"], "out.mkv", mode="protocol")
    assert proto["argv"][proto["argv"].index("-i") + 1] == "concat:a.mp4|b.mp4"
    for bad in ((["a.mp4"], "out.mp4", "demuxer"),
                (["a.mp4", "b.mp4"], "", "demuxer"),
                (["a.mp4", "b.mp4"], "o.mp4", "magic")):
        try:
            concatenate_plan(*bad)
        except VideoCutError:
            pass
        else:
            raise AssertionError(f"bad concat plan not rejected: {bad!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
