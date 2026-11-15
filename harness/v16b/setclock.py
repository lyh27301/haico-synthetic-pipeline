"""Step 16c (root only, in the agent image): set the agent's date. Rewrites the offset constant of libclock.so.1
(harness/v16b/clock.c) to <task date> - <real now> seconds; the new library is written beside the old one and renamed
over it, so running processes keep their mapping and every agent process started afterwards sees the task's date.
  python /opt/.oh16b/setclock.py '2026-03-14 10:00:00'"""
import calendar, os, struct, sys, time

LIB = "/usr/lib/x86_64-linux-gnu/libclock.so.1"
MAGIC = b"OH16C_CLOCK_OFF\0"

when = sys.argv[1].replace("T", " ")[:19]
target = calendar.timegm(time.strptime(when if len(when) > 10 else when + " 09:00:00", "%Y-%m-%d %H:%M:%S"))
offset = target - int(time.time())
data = bytearray(open(LIB, "rb").read())
i = data.find(MAGIC)
assert i >= 0 and data.find(MAGIC, i + 1) < 0, "marker not found exactly once"
data[i + 16:i + 24] = struct.pack("<q", offset)
tmp = LIB + ".new"
with open(tmp, "wb") as f:
    f.write(data)
os.chmod(tmp, 0o755)
os.replace(tmp, LIB)
print(offset)
