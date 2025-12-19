# Bully Anniversary Edition Tex file converter
#
# By aqxua, Continued by Haku (hczn)
#
# 08-16-2025 — 12-19-2025
#
# Usage:
#   pip install pillow
#   python TexConverter.py fileName.tex
#

import struct
import os
import zlib
import sys
from PIL import Image


# ===============================
# Util & Decompression
# ===============================

def READ_U32(f):
    b = f.read(4)
    if len(b) != 4:
        return 0
    return struct.unpack("<I", b)[0]


def DECOMPRESS_BLOCK(f, offset, compress_on_disk):
    f.seek(offset)
    tex_fmt = READ_U32(f)
    w = READ_U32(f)
    h = READ_U32(f)
    mips = READ_U32(f)
    size = READ_U32(f)

    if compress_on_disk:
        _ = READ_U32(f)  
        comp_data = f.read(max(0, size - 4))
        try:
            data = zlib.decompress(comp_data)
        except Exception:
            data = comp_data
    else:
        data = f.read(size)
        if len(data) > 5:
            try:
                orig_len = struct.unpack_from("<I", data, 0)[0]
                dec = zlib.decompress(data[4:])
                if len(dec) == orig_len:
                    data = dec
            except Exception:
                pass

    return tex_fmt, w, h, data


# ===============================
# Pixel Decoder
# ===============================

def DECODE_RGB565(c):
    r = ((c >> 11) & 0x1F) << 3
    g = ((c >> 5) & 0x3F) << 2
    b = (c & 0x1F) << 3
    return (r, g, b)


# FMT3 - BGR16 (RGB565) #

def DECODE_FMT3_BGR16(data, width, height):
    pixels = []
    idx = 0

    for _ in range(width * height):
        if idx + 2 > len(data):
            pixels.append((0, 0, 0, 255))
            continue

        val = struct.unpack_from("<H", data, idx)[0]
        idx += 2

        b = (val & 0x1F) << 3
        g = ((val >> 5) & 0x3F) << 2
        r = ((val >> 11) & 0x1F) << 3

        pixels.append((r, g, b, 255))

    return pixels


# FMT4 - ABGR16 (1-bit alpha) #

def DECODE_FMT4_ABGR16(data, width, height):
    pixels = []
    idx = 0

    for _ in range(width * height):
        if idx + 2 > len(data):
            pixels.append((0, 0, 0, 0))
            continue

        val = struct.unpack_from("<H", data, idx)[0]
        idx += 2

        a = 255 if (val & 0x8000) else 0
        r = ((val >> 10) & 0x1F) << 3
        g = ((val >> 5) & 0x1F) << 3
        b = (val & 0x1F) << 3

        pixels.append((r, g, b, a))

    return pixels


# FMT5 - DXT1 #

def DECODE_FMT5_DXT1(data, width, height):
    pixels = [(0, 0, 0, 255)] * (width * height)
    idx = 0

    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            if idx + 8 > len(data):
                continue

            c0, c1, bits = struct.unpack("<HHI", data[idx:idx + 8])
            idx += 8

            colors = [DECODE_RGB565(c0), DECODE_RGB565(c1)]

            if c0 > c1:
                colors.append(tuple((2 * a + b) // 3 for a, b in zip(colors[0], colors[1])))
                colors.append(tuple((a + 2 * b) // 3 for a, b in zip(colors[0], colors[1])))
            else:
                colors.append(tuple((a + b) // 2 for a, b in zip(colors[0], colors[1])))
                colors.append((0, 0, 0))

            for j in range(16):
                px = bx + (j % 4)
                py = by + (j // 4)
                if px < width and py < height:
                    code = (bits >> (2 * j)) & 0x03
                    pixels[py * width + px] = colors[code] + (255,)

    return pixels


# FMT6 - DXT3 #

def DECODE_FMT6_DXT3(data, width, height):
    pixels = [(0, 0, 0, 0)] * (width * height)
    idx = 0

    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            if idx + 16 > len(data):
                continue

            alphas_raw = data[idx:idx + 8]
            c0, c1, bits = struct.unpack("<HHI", data[idx + 8:idx + 16])
            idx += 16

            cl0 = DECODE_RGB565(c0)
            cl1 = DECODE_RGB565(c1)

            colors = [cl0, cl1]
            if c0 > c1:
                colors.append(tuple((2 * a + b) // 3 for a, b in zip(cl0, cl1)))
                colors.append(tuple((a + 2 * b) // 3 for a, b in zip(cl0, cl1)))
            else:
                colors.append(tuple((a + b) // 2 for a, b in zip(cl0, cl1)))
                colors.append((0, 0, 0))

            for j in range(16):
                px = bx + (j % 4)
                py = by + (j // 4)
                if px < width and py < height:
                    code = (bits >> (2 * j)) & 0x03
                    a = (alphas_raw[j // 2] >> ((j % 2) * 4)) & 0x0F
                    a = (a << 4) | a
                    pixels[py * width + px] = colors[code] + (a,)

    return pixels


# FMT7 - DXT5 #

def DECODE_FMT7_DXT5(data, width, height):
    pixels = [(0, 0, 0, 0)] * (width * height)
    idx = 0

    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            if idx + 16 > len(data):
                continue

            a0, a1 = data[idx], data[idx + 1]
            a_bits = int.from_bytes(data[idx + 2:idx + 8], "little")
            c0, c1, bits = struct.unpack("<HHI", data[idx + 8:idx + 16])
            idx += 16

            colors = [DECODE_RGB565(c0), DECODE_RGB565(c1)]
            colors.append(tuple((2 * a + b) // 3 for a, b in zip(colors[0], colors[1])))
            colors.append(tuple((a + 2 * b) // 3 for a, b in zip(colors[0], colors[1])))

            for j in range(16):
                px = bx + (j % 4)
                py = by + (j // 4)
                if px < width and py < height:
                    code = (bits >> (2 * j)) & 0x03
                    ac = (a_bits >> (3 * j)) & 0x07

                    if a0 > a1:
                        alphas = [
                            a0, a1,
                            (6*a0+a1)//7, (5*a0+2*a1)//7,
                            (4*a0+3*a1)//7, (3*a0+4*a1)//7,
                            (2*a0+5*a1)//7, (a0+6*a1)//7
                        ]
                    else:
                        alphas = [
                            a0, a1,
                            (4*a0+a1)//5, (3*a0+2*a1)//5,
                            (2*a0+3*a1)//5, (a0+4*a1)//5,
                            0, 255
                        ]

                    pixels[py * width + px] = colors[code] + (alphas[ac],)

    return pixels

# PVRTC2 - FMT9 #

def DECODE_FMT9_PVRTC2(data, width, height):
    pixels = [(0, 0, 0, 255)] * (width * height)
    
    block_width = 8
    block_height = 4
    bytes_per_block = 8  # 64bit per block

    blocks_x = (width + block_width - 1) // block_width
    blocks_y = (height + block_height - 1) // block_height

    idx = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            if idx + bytes_per_block > len(data):
                idx += bytes_per_block
                continue

            block = struct.unpack_from("<Q", data, idx)[0]
            idx += bytes_per_block

            color0 = (block >> 0) & 0xFFFF
            color1 = (block >> 16) & 0xFFFF

            c0_r, c0_g, c0_b = DECODE_RGB565(color0)
            c1_r, c1_g, c1_b = DECODE_RGB565(color1)
			# 4 Color interpolation 
            colors = [
                (c0_r, c0_g, c0_b, 255),
                (c1_r, c1_g, c1_b, 255),
                ((2*c0_r + c1_r)//3, (2*c0_g + c1_g)//3, (2*c0_b + c1_b)//3, 255),
                ((c0_r + 2*c1_r)//3, (c0_g + 2*c1_g)//3, (c0_b + 2*c1_b)//3, 255)
            ]

            for py in range(block_height):
                for px in range(block_width):
                    pixel_x = bx * block_width + px
                    pixel_y = by * block_height + py
                    if pixel_x < width and pixel_y < height:
                        bit_idx = py * block_width + px
                        code = (block >> (32 + 2*bit_idx)) & 0x03
                        pixels[pixel_y * width + pixel_x] = colors[code]

    return pixels


# ===============================
# MAIN
# ===============================

def main():
    if len(sys.argv) < 2:
        print("Usage: python TexConverter.py fileName.tex")
        return

    tex_path = sys.argv[1]

    with open(tex_path, "rb") as f:
        ver = READ_U32(f)
        count_plus_1 = READ_U32(f)
        _ = READ_U32(f)
        info_ofs = READ_U32(f)
        count = max(0, count_plus_1 - 1)
        f.seek(16 + (count*4))
        offsets = [READ_U32(f) for _ in range(count)]

        compress_on_disk = False
        if 0 < info_ofs < os.path.getsize(tex_path):
            f.seek(info_ofs)
            info_len = READ_U32(f)
            info_txt = f.read(info_len).decode(errors="ignore").lower()
            if "compressondisk = true" in info_txt:
                compress_on_disk = True

        if count == 0:
            return

        fmt, w, h, data = DECOMPRESS_BLOCK(f, offsets[-1], compress_on_disk)
        print(f"Parsing {tex_path}..")
        print(f"Decompressing {tex_path}..")

        img = None

        if fmt == 0:
            img = Image.frombytes("RGBA", (w, h), data, "raw", "RGBA")
        elif fmt == 1:
            img = Image.frombytes("RGB", (w, h), data, "raw", "BGR")
        elif fmt == 3:
            img = Image.new("RGBA", (w, h))
            img.putdata(DECODE_FMT3_BGR16(data, w, h))
        elif fmt == 4:
            img = Image.new("RGBA", (w, h))
            img.putdata(DECODE_FMT4_ABGR16(data, w, h))
        elif fmt == 5:
            img = Image.new("RGBA", (w, h))
            img.putdata(DECODE_FMT5_DXT1(data, w, h))
        elif fmt == 6:
            img = Image.new("RGBA", (w, h))
            img.putdata(DECODE_FMT6_DXT3(data, w, h))
        elif fmt == 7:
            img = Image.new("RGBA", (w, h))
            img.putdata(DECODE_FMT7_DXT5(data, w, h))
        elif fmt == 8:
            img = Image.frombytes("L", (w, h), data)
        elif fmt == 9:
            pixels = DECODE_FMT9_PVRTC2(data, w, h)
            img = Image.new("RGBA", (w, h))
            img.putdata(pixels)

        if img:
            out_name = os.path.splitext(tex_path)[0] + ".png"
            img.save(out_name)
            print(f"Detail: {tex_path} | {w}x{h} | Format {fmt}")
            print(f"{out_name} was successfully converted\n")
        else:
            print(f"Unsupported Tex file format {fmt}!\n")


if __name__ == "__main__":
    main()
