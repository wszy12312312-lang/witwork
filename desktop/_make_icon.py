"""从 AI 生成的 logo 原图制作桌面图标。

输入：1024x1024 的 logo 原图（右下角带「AI生成」水印）。
处理：
  1) 去水印——图标底板左右对称，把左下角区域水平镜像后贴到右下角，
     边缘 30px 羽化过渡，无痕覆盖水印（含金边弧线）。
  2) 生成多尺寸 .ico（16/24/32/48/64/128/256）。

用法：python _make_icon.py [输入png] [输出目录]
默认输入 = desktop 下最新的 *app_icon*.png，输出 = desktop/assets/
"""
import os
import sys
import glob

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
FEATHER = 30  # 羽化宽度（px）


def find_source():
    if len(sys.argv) > 1:
        return sys.argv[1]
    cands = sorted(glob.glob(os.path.join(BASE, '*app_icon*.png')))
    if not cands:
        cands = sorted(glob.glob(os.path.join(BASE, 'Minimalist*.png')))
    if not cands:
        raise SystemExit('未找到输入 logo（在 desktop/ 下找 *app_icon*.png 或 Minimalist*.png）')
    return cands[-1]


def de_watermark(img):
    """右下角水印 → 用水平镜像的左下角同尺寸区域覆盖（底板对称，接缝羽化）。"""
    w, h = img.size
    pw, ph = 340, 150                     # 覆盖区域尺寸（足够盖住水印+金边弧）
    x0, y0 = w - pw, h - ph
    patch = img.crop((0, y0, pw, h)).transpose(Image.FLIP_LEFT_RIGHT)
    mask = Image.new('L', (pw, ph), 255)
    d = ImageDraw.Draw(mask)
    for i in range(FEATHER):
        a = int(255 * i / FEATHER)
        d.line([(i, 0), (i, ph)], fill=a)   # 左缘渐入
        d.line([(0, i), (pw, i)], fill=a)   # 上缘渐入
    img.paste(patch, (x0, y0), mask)
    return img


def main():
    src_path = find_source()
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'assets')
    os.makedirs(out_dir, exist_ok=True)

    img = Image.open(src_path).convert('RGBA')
    print('输入:', src_path, img.size)
    if img.size[0] != img.size[1]:
        side = min(img.size)
        left = (img.size[0] - side) // 2
        top = (img.size[1] - side) // 2
        img = img.crop((left, top, left + side, top + side))
        print('裁成方形:', img.size)

    clean = de_watermark(img)
    clean_png = os.path.join(out_dir, 'icon-1024.png')
    clean.save(clean_png)
    print('去水印原图:', clean_png)

    ico_path = os.path.join(out_dir, 'icon.ico')
    clean.save(ico_path, format='ICO', sizes=ICO_SIZES)
    print('图标:', ico_path, '内含尺寸:', ', '.join('%dx%d' % s for s in ICO_SIZES))
    print('大小: %.1f KB' % (os.path.getsize(ico_path) / 1024))


if __name__ == '__main__':
    main()
