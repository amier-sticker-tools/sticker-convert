import os, subprocess, tempfile, threading, shutil, glob, gzip, io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from PIL import Image

KEY = os.environ.get("CONVERT_KEY", "")
SEM = threading.Semaphore(2)
FF = ["ffmpeg", "-y", "-loglevel", "error"]

def run(args):
    r = subprocess.run(args, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode()[-400:])

def render_tgs(data, d, size=512, maxfps=15):
    from rlottie_python import LottieAnimation
    p = os.path.join(d, "in.tgs"); open(p, "wb").write(data)
    anim = LottieAnimation.from_tgs(p)
    n = anim.lottie_animation_get_totalframe()
    fps = anim.lottie_animation_get_framerate() or 30
    w, h = size, size
    step = 1
    while fps / step > maxfps: step += 1
    os.makedirs(os.path.join(d, "f"), exist_ok=True)
    k = 0
    for i in range(0, n, step):
        im = anim.render_pillow_frame(frame_num=i, width=w, height=h)
        im.save(os.path.join(d, "f", "%04d.png" % k)); k += 1
    return ["-framerate", str(fps / step), "-i", os.path.join(d, "f", "%04d.png")]

def src_args(kind, data, d, size=512):
    if kind == "tgs":
        return render_tgs(data, d, size)
    p = os.path.join(d, "in.webm"); open(p, "wb").write(data)
    return ["-c:v", "libvpx-vp9", "-i", p]

def convert(kind, fmt, data):
    d = tempfile.mkdtemp()
    try:
        src = src_args(kind, data, d, 384 if fmt in ("gif", "mp4") else (96 if fmt == "tray" else 512))
        out = os.path.join(d, "out")
        if fmt == "gif":
            vf = "fps=15,scale=384:384:force_original_aspect_ratio=decrease:flags=lanczos,split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=alpha_threshold=128"
            run(FF + src + ["-vf", vf, "-loop", "0", out + ".gif"]); return open(out + ".gif", "rb").read(), "image/gif"
        if fmt == "mp4":
            vf = "fps=30,scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p"
            # flatten alpha on a white background
            fc = "color=c=white:s=384x384:r=15[bg];[0:v]fps=15,scale=384:384:force_original_aspect_ratio=decrease:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p"
            run(FF + src + ["-filter_complex", fc, "-c:v", "libx264", "-movflags", "+faststart", "-an", out + ".mp4"]); return open(out + ".mp4", "rb").read(), "video/mp4"
        if fmt in ("awebp", "wa"):
            wa = fmt == "wa"
            best = None
            for q, fps in ((70, 15), (50, 12), (35, 10), (22, 8), (12, 8)):
                vf = f"fps={fps},scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,format=rgba" if wa else f"fps={fps},scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba"
                run(FF + src + ["-t", "9.5", "-vf", vf, "-c:v", "libwebp", "-lossless", "0", "-q:v", str(q), "-compression_level", "4", "-loop", "0", "-an", out + ".webp"])
                best = open(out + ".webp", "rb").read()
                if not wa or len(best) <= 500000: break
            return best, "image/webp"
        if fmt == "tray":
            # first frame as 96x96 png on transparent
            run(FF + src + ["-frames:v", "1", "-vf", "scale=96:96:force_original_aspect_ratio=decrease,pad=96:96:(ow-iw)/2:(oh-ih)/2:color=0x00000000,format=rgba", out + ".png"])
            return open(out + ".png", "rb").read(), "image/png"
        raise ValueError("bad fmt")
    finally:
        shutil.rmtree(d, ignore_errors=True)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ct="text/plain"):
        self.send_response(code); self.send_header("content-type", ct); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self): self._send(200, b"ok")
    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not KEY or self.headers.get("x-key") != KEY: return self._send(403, b"forbidden")
        n = int(self.headers.get("content-length", 0))
        if n > 5_000_000: return self._send(413, b"too big")
        data = self.rfile.read(n)
        try:
            with SEM:
                out, ct = convert(q.get("kind", ["webm"])[0], q.get("fmt", ["gif"])[0], data)
            self._send(200, out, ct)
        except Exception as e:
            self._send(500, str(e).encode()[:500])

ThreadingHTTPServer(("0.0.0.0", 7860), H).serve_forever()
