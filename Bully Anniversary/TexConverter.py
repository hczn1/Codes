# Bully Anniversary Edition Tex file converter
# --------------------------------------------
# By Haku [hczn]

import struct
import os
import zlib
import sys
from PIL import Image

# Util & Decompression

def read_u32(f):
    b = f.read(4)
    if len(b) != 4: return 0
    return struct.unpack("<I", b)[0]

def decompress_block(f, offset, compress_on_disk):
    f.seek(offset)
    tex_fmt = read_u32(f)
    w = read_u32(f)
    h = read_u32(f)
    mips = read_u32(f)
    size = read_u32(f)
    
    if compress_on_disk:
        dec_size = read_u32(f)
        comp_data = f.read(max(0, size - 4))
        try:
            data = zlib.decompress(comp_data)
        except:
            data = comp_data
    else:
        data = f.read(size)
        
        if len(data) > 5:
            try:
                orig_len = struct.unpack_from("<I", data, 0)[0]
                dec = zlib.decompress(data[4:])
                if len(dec) == orig_len:
                    data = dec
            except:
                pass
    return tex_fmt, w, h, data

# DXT Decoder
	
def decode_rgb565(c):
    r = ((c >> 11) & 0x1F) << 3
    g = ((c >> 5) & 0x3F) << 2
    b = (c & 0x1F) << 3
    return (r, g, b)

def decode_dxt1(data, width, height):
    pixels = [(0,0,0,255)] * (width * height)
    idx = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            if idx + 8 > len(data): continue
            c0, c1, bits = struct.unpack("<HHI", data[idx:idx+8])
            idx += 8
            colors = [decode_rgb565(c0), decode_rgb565(c1)]
            if c0 > c1:
                colors.append(tuple((2*c0_ + c1_)//3 for c0_,c1_ in zip(colors[0],colors[1])))
                colors.append(tuple((c0_ + 2*c1_)//3 for c0_,c1_ in zip(colors[0],colors[1])))
            else:
                colors.append(tuple((c0_ + c1_)//2 for c0_,c1_ in zip(colors[0],colors[1])))
                colors.append((0,0,0))
            for j in range(16):
                px, py = bx + j%4, by + j//4
                if px < width and py < height:
                    code = (bits >> (2*j)) & 0x03
                    pixels[py*width + px] = colors[code] + (255,)
    return pixels

def decode_dxt5(data, width, height):
    pixels = [(0,0,0,0)] * (width * height)
    idx = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            if idx + 16 > len(data): continue
            a0, a1 = data[idx], data[idx+1]
            a_bits = int.from_bytes(data[idx+2:idx+8], 'little')
            c0, c1, bits = struct.unpack("<HHI", data[idx+8:idx+16])
            idx += 16
            colors = [decode_rgb565(c0), decode_rgb565(c1)]
            colors.append(tuple((2*c0_+c1_)//3 for c0_,c1_ in zip(colors[0],colors[1])))
            colors.append(tuple((c0_+2*c1_)//3 for c0_,c1_ in zip(colors[0],colors[1])))
            for j in range(16):
                px, py = bx + j%4, by + j//4
                if px < width and py < height:
                    code = (bits >> (2*j)) & 0x03
                    a_code = (a_bits >> (3*j)) & 0x07
                    alphas = [a0, a1, (6*a0+a1)//7, (5*a0+2*a1)//7, (4*a0+3*a1)//7, (3*a0+4*a1)//7, (2*a0+5*a1)//7, (a0+6*a1)//7] if a0 > a1 else \
                             [a0, a1, (4*a0+a1)//5, (3*a0+2*a1)//5, (2*a0+3*a1)//5, (a0+4*a1)//5, 0, 255]
                    pixels[py*width + px] = colors[code] + (alphas[a_code],)
    return pixels

# MAIN

def main():
    if len(sys.argv) < 2:
        print("Usage: python TexConverter.py fileName.tex")
        return

    tex_path = sys.argv[1]
    with open(tex_path, "rb") as f:
    	
        # Header parsing
        
        ver = read_u32(f)
        count_plus_1 = read_u32(f)
        file_id = read_u32(f)
        info_ofs = read_u32(f)
        count = max(0, count_plus_1 - 1)

        f.seek(16 + (count * 4))
        offsets = [read_u32(f) for _ in range(count)]
        compress_on_disk = False
        if 0 < info_ofs < os.path.getsize(tex_path):
            f.seek(info_ofs)
            info_len = read_u32(f)
            info_txt = f.read(info_len).decode(errors="ignore").lower()
            if "compressondisk = true" in info_txt:
                compress_on_disk = True

        if count == 0: return

        idx = count - 1
        fmt, w, h, data = decompress_block(f, offsets[idx], compress_on_disk)
        print(f"Format: {fmt} | Size: {w}x{h}")

        img = None
        if fmt == 0: # RGBA8888 - Uncompressed zlib
            img = Image.frombytes("RGBA", (w, h), data, "raw", "RGBA")
        elif fmt == 1: # RGB888 - ?
            img = Image.frombytes("RGB", (w, h), data, "raw", "BGR")
        elif fmt == 5: # DXT1 - Original tex file ?
            pixels = decode_dxt1(data, w, h)
            img = Image.new("RGBA", (w, h)); img.putdata(pixels)
        elif fmt == 7: # DXT5 - Compressed zlib
            pixels = decode_dxt5(data, w, h)
            img = Image.new("RGBA", (w, h)); img.putdata(pixels)
        elif fmt == 8: # Alpha8 - ?
            img = Image.frombytes("L", (w, h), data)
        
        if img:
            out_name = os.path.splitext(tex_path)[0] + ".png"
            img.save(out_name)
            print(f"Done converting: {out_name}")
        else:
            print(f"Unsupported {fmt} format")

if __name__ == "__main__":
    main()
