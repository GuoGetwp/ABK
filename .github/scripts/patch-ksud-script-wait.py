#!/usr/bin/env python3
"""Carry ABK's local fix for an upstream ksud compile break until upstream lands it.

Upstream 932d9bd2 ("ksud: add timeout for boot stage scripts", #3797) replaced
run_stage's `block: bool` with `wait: ScriptWait` so stage scripts can time out, but
left one call site still naming `block`:

    if let Err(e) = crate::module::exec_stage_lua(stage, block, "kernelsu") {

That line is gated on `cfg(all(target_os = "android", target_arch = "aarch64"))`, so
upstream's own CI never compiles it. Only an Android cross-build reaches it, which is
what this repo's app builds do -- so an upstream refactor that upstream's CI accepts
breaks us.

exec_stage_lua still takes a plain bool and forwards it to run_lua, whose parameter is
named `_wait` and never read. Any bool therefore preserves current behaviour. The two
non-blocking callers pass NoWait, so mapping NoWait -> false and everything else -> true
reproduces the pre-932d9bd2 calls exactly.

Delete this patch (and its call sites in the two app workflows) once upstream main
compiles this path again. The script is a no-op after that, by design.
"""
from __future__ import annotations

import pathlib
import sys


BROKEN = 'crate::module::exec_stage_lua(stage, block, "kernelsu")'
MARKER = "ABK upstream fix: 932d9bd2 left exec_stage_lua(stage, block, ...) behind"

ORIGINAL = f"""    // run lua stage script
    #[cfg(all(target_os = "android", target_arch = "aarch64"))]
    if let Err(e) = {BROKEN} {{
"""

PATCHED = f"""    // run lua stage script
    // {MARKER}
    #[cfg(all(target_os = "android", target_arch = "aarch64"))]
    if let Err(e) = crate::module::exec_stage_lua(stage, !matches!(wait, ScriptWait::NoWait), "kernelsu") {{
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-ksud-script-wait.py <sukisu-source-dir>", file=sys.stderr)
        return 2

    source_dir = pathlib.Path(sys.argv[1]).resolve()
    target = source_dir / "userspace" / "ksud" / "src" / "init_event.rs"
    if not target.is_file():
        # A moved or renamed file is an incompatibility worth failing on, unlike the
        # fixed-code case below.
        print(f"::error::{target} not found", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"ksud script-wait patch already present: {target}")
        return 0

    if BROKEN not in text:
        # The broken form is gone, so either upstream fixed it or refactored the call
        # past it. Either way there is nothing to carry -- and failing here would turn
        # the fix into a build break at exactly the moment it stops being needed.
        print(f"::warning::no exec_stage_lua(stage, block, ...) call to patch in {target}; nothing to do")
        return 0

    if ORIGINAL not in text:
        print(f"::error::exec_stage_lua(stage, block, ...) found in {target} but its surrounding block does not match", file=sys.stderr)
        return 1

    target.write_text(text.replace(ORIGINAL, PATCHED), encoding="utf-8")
    print(f"patched ksud run_stage lua call: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())