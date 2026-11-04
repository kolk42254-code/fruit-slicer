"""One-time test setup. Downloads what the tests need into tests/vendor (not committed) and builds the
fake-camera videos into tests/videos (not committed):

  1. @mediapipe/tasks-vision 1.1.1 (the hand tracker code the game loads from the CDN)
  2. the official hand model (float16/1), checked against its SHA-256
  3. test media from github.com/spmallick/learnopencv (HandPose: front-back.jpg, asl.mp4); used only for
     local testing, never committed or shipped (its licence is not stated)
  4. fake-camera y4m videos + swipe frames (tests/make_videos.py, needs ffmpeg)
  5. ground truth from Python MediaPipe: videos/gt.json and videos/swipe_landmarks.json

    python tests/get_assets.py
"""
import hashlib, io, json, os, subprocess, sys, tarfile, urllib.request

TESTS = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(TESTS, 'vendor')
MEDIA = os.path.join(VENDOR, 'media')
VID = os.path.join(TESTS, 'videos')
MODEL = os.path.join(VENDOR, 'hand_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_SHA = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'   # same file the app build downloads
NPM_TGZ = 'https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.1.1.tgz'
MEDIA_FILES = {  # name: (url, sha256)
    'front-back.jpg': ('https://raw.githubusercontent.com/spmallick/learnopencv/master/HandPose/front-back.jpg',
                       'cdbc3e9d75996913'),
    'asl.mp4': ('https://raw.githubusercontent.com/spmallick/learnopencv/master/HandPose/asl.mp4', 'bb779d0e620373f6'),
}


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'fruit-slicer-tests'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.makedirs(MEDIA, exist_ok=True)
    os.makedirs(VID, exist_ok=True)

    pkg = os.path.join(VENDOR, 'tasks-vision')
    if not os.path.exists(os.path.join(pkg, 'wasm', 'vision_wasm_internal.wasm')):
        print('downloading @mediapipe/tasks-vision 1.1.1 ...')
        with tarfile.open(fileobj=io.BytesIO(get(NPM_TGZ)), mode='r:gz') as t:
            for m in t.getmembers():
                if m.isfile() and m.name.startswith('package/'):
                    dst = os.path.join(pkg, m.name[len('package/'):])
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    open(dst, 'wb').write(t.extractfile(m).read())

    if not os.path.exists(MODEL) or sha(open(MODEL, 'rb').read()) != MODEL_SHA:
        print('downloading the hand model ...')
        data = get(MODEL_URL)
        if sha(data) != MODEL_SHA:
            sys.exit('hand model SHA-256 does not match the known official file')
        open(MODEL, 'wb').write(data)

    for name, (url, want) in MEDIA_FILES.items():
        path = os.path.join(MEDIA, name)
        if not os.path.exists(path):
            print('downloading', name, '...')
            data = get(url)
            if not sha(data).startswith(want):
                sys.exit(f'{name}: unexpected file (SHA-256 {sha(data)[:16]})')
            open(path, 'wb').write(data)

    if not os.path.exists(os.path.join(VID, 'dark_one.y4m')):
        print('building fake-camera videos (needs ffmpeg) ...')
        subprocess.run([sys.executable, os.path.join(TESTS, 'make_videos.py')], check=True)

    print('computing ground truth with Python MediaPipe ...')
    import cv2, mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    det = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=MODEL), num_hands=2, running_mode=vision.RunningMode.IMAGE))

    def detect(path):
        img = cv2.imread(path)
        h, w = img.shape[:2]
        res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        return [[(p.x * w, p.y * h) for p in lm] for lm in res.hand_landmarks]

    gt = {}
    for name in ('static_one', 'two_static', 'portrait_one'):
        hands = detect(os.path.join(VID, name + '_frame0.jpg'))
        gt[name] = sorted([[round(h[8][0], 1), round(h[8][1], 1)] for h in hands])
    json.dump(gt, open(os.path.join(VID, 'gt.json'), 'w'), indent=1)
    lm = {}
    for i in (1, 18, 31, 32, 51, 52):
        hands = detect(os.path.join(VID, 'frames', 'swipe_sharp', f'f{i:03d}.png'))
        lm[str(i)] = {str(k): [round(hands[0][k][0], 1), round(hands[0][k][1], 1)] for k in (0, 5, 8, 17)} if hands else {}
    json.dump(lm, open(os.path.join(VID, 'swipe_landmarks.json'), 'w'))
    print('ground truth:', json.dumps(gt))
    print('test assets ready')


if __name__ == '__main__':
    main()
