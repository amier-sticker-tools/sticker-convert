import os, io, json, time, zipfile, urllib.request, concurrent.futures as cf
from app import convert

BASE = os.environ["WORKER_URL"]; KEY = os.environ["CONVERT_KEY"].strip(); JOB = os.environ["JOB"]
T0 = time.time()

def call(path, data=None):
    err = None
    for _ in range(3):
        try:
            r = urllib.request.Request(BASE + path, data=data, headers={"x-key": KEY, "user-agent": "gh-runner"})
            return urllib.request.urlopen(r, timeout=120).read()
        except Exception as e:
            err = e; time.sleep(1)
    raise err

try:
    spec = json.loads(call(f"/gh/job?id={JOB}"))
    fmt = spec["fmt"]
    ext = {"awebp": "webp", "wa": "webp"}.get(fmt, fmt)
    def one(i):
        it = spec["items"][i]
        data = call(f"/gh/file?id={JOB}&i={i}")
        out = convert(it["kind"], fmt, data)[0]
        tray = convert(it["kind"], "tray", data)[0] if (i == 0 and fmt == "wa") else None
        return i, out, tray
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, range(len(spec["items"]))))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, out, tray in res:
            z.writestr(f"{spec.get('start', 0) + i + 1}.{ext}", out)
            if tray: z.writestr("tray.png", tray)
        if fmt == "wa":
            z.writestr("title.txt", spec["label"][:128]); z.writestr("author.txt", "@T1UU1")
    secs = round(time.time() - T0, 1)
    print("converted", len(res), "stickers in", secs, "s; zip bytes", buf.tell())
    call(f"/gh/done?id={JOB}&secs={secs}", buf.getvalue())
except Exception as e:
    print("failed:", type(e).__name__, str(e)[:200])
    try: call(f"/gh/fail?id={JOB}", b"x")
    except Exception: pass
    raise SystemExit(1)
