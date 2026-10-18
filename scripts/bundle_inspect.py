"""List the objects inside Unity asset bundles (type counts, textures, sprites, clips).

usage: python -P -E bundle_inspect.py <bundle> [<bundle> ...]
"""
import collections
import sys

import UnityPy


def main():
    for path in sys.argv[1:]:
        env = UnityPy.load(path)
        print(f"===== {path}")
        for name, f in env.files.items():
            print(f"  file: {name} ({type(f).__name__})")
        counts = collections.Counter(o.type.name for o in env.objects)
        print("  types:", dict(counts))
        for o in env.objects:
            t = o.type.name
            if t in ("Texture2D", "SpriteAtlas", "AnimationClip", "AnimatorController", "AnimatorOverrideController",
                     "GameObject", "SpriteRenderer", "SkinnedMeshRenderer", "MeshRenderer", "Material"):
                try:
                    d = o.read()
                except Exception as e:  # noqa: BLE001
                    print(f"    {t} path_id={o.path_id} <read error {e}>")
                    continue
                name = getattr(d, "m_Name", "")
                extra = ""
                if t == "Texture2D":
                    extra = f" {d.m_Width}x{d.m_Height} fmt={d.m_TextureFormat}"
                elif t == "SpriteAtlas":
                    extra = f" packed={len(d.m_PackedSprites)}"
                print(f"    {t:22s} {o.path_id:>20d} {name}{extra}")
        sprites = [o for o in env.objects if o.type.name == "Sprite"]
        if sprites:
            names = []
            for o in sprites[:12]:
                try:
                    names.append(o.read().m_Name)
                except Exception:  # noqa: BLE001
                    names.append("?")
            print(f"  sprites: {len(sprites)} e.g. {names}")


if __name__ == "__main__":
    main()
