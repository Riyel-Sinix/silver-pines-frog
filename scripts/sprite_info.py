"""Print Sprite/Texture2D details for sprites whose name matches a substring.

usage: python -P -E sprite_info.py <bundle> <name-substring> [max]
"""
import sys

import UnityPy


def main():
    env = UnityPy.load(sys.argv[1])
    key = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    shown = 0
    for o in env.objects:
        if o.type.name != "Sprite":
            continue
        s = o.read()
        if key not in s.m_Name:
            continue
        rd = s.m_RD
        tex = rd.texture.read()
        vd = rd.m_VertexData
        print(f"--- {s.m_Name}")
        print(f"  rect={s.m_Rect} pivot={s.m_Pivot} ppu={s.m_PixelsToUnits} offset={s.m_Offset} isPolygon={getattr(s, 'm_IsPolygon', None)}")
        print(f"  RD.textureRect={rd.textureRect} textureRectOffset={rd.textureRectOffset} settingsRaw={rd.settingsRaw} uvTransform={rd.uvTransform}")
        print(f"  vertices={vd.m_VertexCount} indexBytes={len(rd.m_IndexBuffer)} channels={[(c.stream, c.offset, c.format, c.dimension) for c in vd.m_Channels]}")
        print(f"  secondaryTextures={[getattr(t, 'name', None) for t in getattr(rd, 'secondaryTextures', [])]}")
        print(f"  texture={tex.m_Name} {tex.m_Width}x{tex.m_Height} fmt={tex.m_TextureFormat} mips={tex.m_MipCount} stream={tex.m_StreamData.path!r}:{tex.m_StreamData.size}")
        shown += 1
        if shown >= limit:
            break


if __name__ == "__main__":
    main()
