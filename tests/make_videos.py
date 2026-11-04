"""Builds the fake-camera videos (y4m) and swipe frames the camera tests use, from a photo of two hands
(front-back.jpg) and a short webcam clip (asl.mp4) from the LearnOpenCV HandPose folder on GitHub.
Run by tests/get_assets.py. Needs: numpy, opencv-python, ffmpeg on PATH."""
import json, os, subprocess
import cv2
import numpy as np

TESTS = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(TESTS, 'vendor', 'media')
VID = os.path.join(TESTS, 'videos')
os.makedirs(os.path.join(VID, 'frames', 'swipe_sharp'), exist_ok=True)
os.makedirs(os.path.join(VID, 'frames', 'swipe_blur'), exist_ok=True)
rng = np.random.default_rng(7)

src = cv2.imread(os.path.join(MEDIA, 'front-back.jpg'))            # 1200x800, two hands on white
# crop hand A (palm). Python MediaPipe: tip8=(383.0, 99.8), bbox (123,66)-(530,656)
x0, y0, x1, y1 = 90, 30, 570, 720
crop = src[y0:y1, x0:x1]
S = 260 / crop.shape[0]                                              # hand ~260 px tall in a 640x480 frame
crop = cv2.resize(crop, (round(crop.shape[1] * S), round(crop.shape[0] * S)), interpolation=cv2.INTER_AREA)
tip_in_crop = ((383.0 - x0) * S, (99.8 - y0) * S)
bg_color = np.median(np.concatenate([crop[:5].reshape(-1, 3), crop[-5:].reshape(-1, 3)]), axis=0)
ch, cw = crop.shape[:2]


def frame_with(w, h, px, py, blur=0):
    M = np.float32([[1, 0, px], [0, 1, py]])                         # sub-pixel placement
    f = cv2.warpAffine(crop.astype(np.float32), M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bg_color.tolist())
    if blur > 1:
        k = np.zeros((1, int(blur)), np.float32); k[:] = 1.0 / int(blur)
        f = cv2.filter2D(f, -1, k)                                    # horizontal motion blur
    f = f + rng.normal(0, 3.0, f.shape)                               # sensor noise -> realistic landmark jitter
    return np.clip(f, 0, 255).astype(np.uint8)


def write_y4m(name, frames, fps=30):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
                          '-pix_fmt', 'yuv420p', os.path.join(VID, name + '.y4m')], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close(); p.wait()
    cv2.imwrite(os.path.join(VID, name + '_frame0.jpg'), frames[0])


meta = {'tip_in_crop': tip_in_crop, 'crop_size': [cw, ch]}
# 1) one still hand, 640x480, with +-0.4 px wobble
frames = [frame_with(640, 480, 300 + rng.uniform(-0.4, 0.4), 150 + rng.uniform(-0.4, 0.4)) for _ in range(60)]
write_y4m('static_one', frames)
meta['static_one'] = {'size': [640, 480], 'tip': [300 + tip_in_crop[0], 150 + tip_in_crop[1]]}


# 2) swipe: hold left 18 frames, move right 8 frames (blurred in swipe_blur), hold right 18, move back 8
def swipe(name, blur_on):
    xs = []
    L, R = 60.0, 420.0
    xs += [L] * 18
    xs += [L + (R - L) * (k + 1) / 8 for k in range(8)]
    xs += [R] * 18
    xs += [R - (R - L) * (k + 1) / 8 for k in range(8)]
    fr = []
    for i, x in enumerate(xs):
        moving = (18 <= i < 26) or (44 <= i < 52)
        fr.append(frame_with(640, 480, x, 140, blur=(15 if (moving and blur_on) else 0)))
    write_y4m(name, fr)
    # the frames as the camera delivers them (through YUV 4:2:0), for the frame-by-frame tests
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', os.path.join(VID, name + '.y4m'), os.path.join(VID, 'frames', name, 'f%03d.png')], check=True)
    return {'size': [640, 480], 'tip_y': 140 + tip_in_crop[1], 'tip_x_left': L + tip_in_crop[0], 'tip_x_right': R + tip_in_crop[0], 'frames': len(xs)}


meta['swipe_sharp'] = swipe('swipe_sharp', False)
meta['swipe_blur'] = swipe('swipe_blur', True)

# 3) two hands: the whole photo scaled to 640 wide, centred on 640x480
s2 = 640 / src.shape[1]
two = cv2.resize(src, (640, round(src.shape[0] * s2)), interpolation=cv2.INTER_AREA)
pad = (480 - two.shape[0]) // 2
base = np.empty((480, 640, 3), np.uint8); base[:] = bg_color; base[pad:pad + two.shape[0]] = two
frames = [np.clip(base + rng.normal(0, 3.0, base.shape), 0, 255).astype(np.uint8) for _ in range(60)]
write_y4m('two_static', frames)
meta['two_static'] = {'size': [640, 480], 'tips': [[383.0 * s2, 99.8 * s2 + pad], [839.5 * s2, 110.3 * s2 + pad]]}

# 4) phone portrait 480x640
frames = [frame_with(480, 640, 150 + rng.uniform(-0.4, 0.4), 220 + rng.uniform(-0.4, 0.4)) for _ in range(60)]
write_y4m('portrait_one', frames)
meta['portrait_one'] = {'size': [480, 640], 'tip': [150 + tip_in_crop[0], 220 + tip_in_crop[1]]}

# 5) no hand: plain background + noise
frames = []
for _ in range(30):
    f = np.empty((480, 640, 3), np.float32); f[:] = bg_color
    frames.append(np.clip(f + rng.normal(0, 3.0, f.shape), 0, 255).astype(np.uint8))
write_y4m('nohand', frames)

# 6) a real webcam-style clip (ASL signer), converted as-is
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', os.path.join(MEDIA, 'asl.mp4'), '-pix_fmt', 'yuv420p', '-r', '30', os.path.join(VID, 'asl.y4m')], check=True)

# 7) a dark room: the still hand at about 17% brightness
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', os.path.join(VID, 'static_one.y4m'), '-vf', 'lutyuv=y=val*0.17:u=128+(val-128)*0.6:v=128+(val-128)*0.6',
                '-pix_fmt', 'yuv420p', os.path.join(VID, 'dark_one.y4m')], check=True)

json.dump(meta, open(os.path.join(VID, 'meta.json'), 'w'), indent=1)
print('fake-camera videos written to', VID)
