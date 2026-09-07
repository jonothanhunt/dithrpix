# Probes

Run against the badge in normal mode (not disk mode), with the REPL available:

```bash
mpremote connect /dev/ttyACM0 run tools/probe_power.py
```

`mpremote run` executes the script on the device without writing anything to
it. Each probe prints its findings; several also leave files on `/` for pulling
back with `mpremote ... fs cp`.

| Probe | Question it answers | Outcome |
| --- | --- | --- |
| `probe_power.py` | What sleep/wake/power API exists? | Found `powman`'s wake reasons — the fix for battery wake |
| `probe_downsize.py` | Does the camera's downsize work? | Misleading: wrote to the *read* register |
| `probe_downsize2.py` | Retry with the datasheet's detailed opcodes | Also wrong; the docs contradict themselves |
| `probe_raw.py` | What do 0x53/0x54/0x55 actually do? | Settled it: downsize is not implemented |
| `probe_settle.py` | Is `frame_length` read too early? | No — but exposed the 8-byte truncation |
| `probe_ab.py` | 160x120 vs 320x240, same scene | 320x240 carries ~4x the detail |
| `probe_stable.py` | Is 320x240 stable? Does `blit` average? | Stable; `blit` is nearest-neighbour |
| `probe_startup.py` | Which camera init step is slow/failing? | Full init ~1.8s, frame ~1.4s |
| `probe_hang.py` | Is the camera or the dither blocking? | Neither — both fine |
| `probe_scale.py` | Does `blit` average when shrinking? | **Crashes the board** — allocates 307KB and scans it in pure Python |
| `probe_dither.py` | Which firmware dither filters are usable? | **Crashes the board** — guesses native signatures |

The last two are kept as cautionary examples. `probe_dither.py` in particular
calls native functions with invented argument lists, which hard-faults rather
than raising — do not run it without reading it.

`pull_photos.sh` copies the photos off `/`, which disk mode cannot see.
