import os, io, json, time, zipfile, subprocess, urllib.request, concurrent.futures as cf
from app import convert

BASE = os.environ["WORKER_URL"]; KEY = os.environ["CONVERT_KEY"].strip(); JOB = os.environ["JOB"]
T0 = time.time()

def work(a):
    kind, fmt, data, tray = a
    out = convert(kind, fmt, data)[0]
    return out, (convert(kind, "tray", data)[0] if tray else None)

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
    if any(x["kind"] != "tgs" for x in spec["items"]) and subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        subprocess.run("sudo apt-get update -qq && sudo apt-get install -y -qq --no-install-recommends ffmpeg", shell=True, check=True)
    with cf.ThreadPoolExecutor(8) as ex:
        datas = list(ex.map(lambda i: call(f"/gh/file?id={JOB}&i={i}"), range(len(spec["items"]))))
    jobs = [(spec["items"][i]["kind"], fmt, datas[i], i == 0 and fmt == "wa") for i in range(len(datas))]
    with cf.ProcessPoolExecutor(4) as ex:
        res = [(i,) + r for i, r in enumerate(ex.map(work, jobs))]
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
