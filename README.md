    # SigmaOS-video-cut

    Lossless-ish video trimmer

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/omacom/omacut

    ## Design principles applied
    - **Separation of Concerns**
- **Defensive Programming**
- **Fail-Fast**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `probe-plan, cut-plan, validate-range, concatenate-plan`

    ```
    $ sigma-cut probe-plan talk.mp4
ffprobe -v error -print_format json -show_format -show_streams talk.mp4
$ sigma-cut validate-range --start 10 --end 60 --duration 612.34
ok: 50.000s window (10.000s .. 60.000s of 612.34s)
$ sigma-cut cut-plan talk.mp4 --start 10 --end 60 --out part.mp4
ffmpeg -hide_banner -loglevel error -y -ss 10.000 -i talk.mp4 -t 50.000 -c copy part.mp4
$ sigma-cut concatenate-plan a.mp4 b.mp4 --out movie.mp4

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
