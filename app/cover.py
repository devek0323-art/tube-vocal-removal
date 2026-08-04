# 노래방 영상의 정지 배경 한 장을 합성한다 (썸네일 블러 + 앨범아트 + 반사 + 곡 정보)
from pathlib import Path

W, H = 1280, 720
ART = 232                   # 앨범아트 한 변
ART_TOP = 47
REFLECT = 70                # 반사 높이
PLATE_TOP = 372
PLATE_MIN_W = 380
BACKDROP_TARGET = 34        # 배경 평균 밝기(0~255). 흰 썸네일이 와도 가사가 읽히게 맞춘다.

FONT = Path(__file__).resolve().parent / "assets" / "Pretendard.ttf"


def _font(size, weight):
    from PIL import ImageFont

    font = ImageFont.truetype(str(FONT), size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass                # 가변 축이 없는 폰트로 대체된 경우
    return font


def _trim_bars(image, tolerance=14):
    """레터박스(위아래 검은 띠)를 잘라낸다. 썸네일은 영상 캡처라 띠가 흔하다."""
    import numpy as np

    rows = np.asarray(image.convert("RGB"), dtype=int).reshape(image.height, -1, 3)
    bar = (rows.std(axis=(1, 2)) < tolerance) & (rows.mean(axis=(1, 2)) < 36)
    top, bottom = 0, len(bar)
    while top < bottom and bar[top]:
        top += 1
    while bottom > top and bar[bottom - 1]:
        bottom -= 1
    if bottom - top < image.height * 0.4:        # 지나치게 잘리면 원본을 쓴다
        return image
    return image.crop((0, top, image.width, bottom))


def _square(image, size):
    from PIL import Image

    image = _trim_bars(image)
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    return image.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)


def _backdrop(source):
    """썸네일을 화면 가득 채워 흐리게 깔고, 밝기를 재서 목표치까지 낮춘 뒤 비네트."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    scale = max(W / source.width, H / source.height) * 1.25
    big = source.resize((int(source.width * scale), int(source.height * scale)), Image.LANCZOS)
    left, top = (big.width - W) // 2, (big.height - H) // 2
    canvas = big.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(46))

    # 고정 비율로 깎으면 흰 썸네일은 여전히 밝다. 실제 밝기를 재서 맞춘다.
    mean = float(np.asarray(canvas.convert("L"), dtype=float).mean())
    canvas = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), canvas,
                         min(1.0, BACKDROP_TARGET / max(mean, 1.0)))

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((-W * 0.30, -H * 0.42, W * 1.30, H * 1.34), fill=255)
    return Image.composite(canvas, Image.new("RGB", (W, H), (0, 0, 0)),
                           mask.filter(ImageFilter.GaussianBlur(150)))


def _reflection(art):
    """아래로 갈수록 사라지는 반사."""
    from PIL import Image

    flipped = art.transpose(Image.FLIP_TOP_BOTTOM).crop((0, 0, art.width, REFLECT)).convert("RGBA")
    gradient = Image.linear_gradient("L").resize((art.width, REFLECT))
    flipped.putalpha(gradient.point(lambda v: int((255 - v) * 0.34)))
    return flipped


def _plate(canvas, artist, track):
    """곡 정보 — 채움 없이 테두리만. 뒤에 넓은 그림자를 깔아 배경에 묻히지 않게."""
    from PIL import Image, ImageDraw, ImageFilter

    big, small = _font(36, 720), _font(17, 450)
    layer = canvas.convert("RGBA")
    draw = ImageDraw.Draw(layer, "RGBA")
    width = max(PLATE_MIN_W, int(max(draw.textlength(track, font=big),
                                     draw.textlength(artist, font=small))) + 108)
    box = ((W - width) // 2, PLATE_TOP, (W + width) // 2, PLATE_TOP + 104)

    glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(box, radius=3, fill=(0, 0, 0, 150))
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(20)))

    draw = ImageDraw.Draw(layer, "RGBA")
    draw.rounded_rectangle(box, radius=3, outline=(255, 255, 255, 62), width=1)
    draw.text((W // 2, PLATE_TOP + 15), track, font=big, fill=(255, 255, 255), anchor="ma")
    draw.text((W // 2, PLATE_TOP + 63), artist, font=small, fill=(178, 172, 163), anchor="ma")
    return layer.convert("RGB")


def compose(thumbnail, artist, track, destination):
    """배경 한 장을 만들어 저장한다. 썸네일이 없으면 어두운 바탕으로."""
    from PIL import Image, ImageDraw, ImageFilter

    canvas = Image.new("RGB", (W, H), (16, 19, 24))
    if thumbnail and Path(thumbnail).is_file():
        source = Image.open(thumbnail).convert("RGB")
        canvas = _backdrop(source)
        art = _square(source, ART)
        # 곡이 하나뿐이라 좌우에 같은 그림을 세우면 배경과 뒤엉킨다. 한 장만 두고
        # 그림자로 띄운다.
        left = (W - ART) // 2
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle(
            (left - 6, ART_TOP - 2, left + ART + 6, ART_TOP + ART + 12), fill=(0, 0, 0, 190))
        canvas = Image.alpha_composite(canvas.convert("RGBA"),
                                       shadow.filter(ImageFilter.GaussianBlur(18))).convert("RGB")
        canvas.paste(art, (left, ART_TOP))
        reflection = _reflection(art)
        canvas.paste(reflection, (left, ART_TOP + ART), reflection)
        ImageDraw.Draw(canvas).rectangle((left, ART_TOP, left + ART - 1, ART_TOP + ART - 1),
                                         outline=(255, 255, 255, 58), width=1)

    canvas = _plate(canvas, artist, track)
    canvas.save(destination)
    return destination
