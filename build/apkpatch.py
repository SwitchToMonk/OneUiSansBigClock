"""Rename the package of a compiled (binary-XML) APK and touch up its strings.

AndroidManifest.xml is a binary XML chunk file: a ResXMLTree header, a string
pool, a resource map, then nodes. Attribute values reference strings by *index*,
never by offset, so replacing strings means rebuilding the string pool and
leaving every node untouched - only the file's total size changes.

resources.arsc is the same trick: a ResTable header, then the global value
string pool, then package chunks. Same rebuild applies; the resource package
name inside the package chunk is a fixed 128-unit UTF-16 field, patched in
place.
"""
import struct
import sys


# ---------------------------------------------------------------- string pool
def _decode_len_utf8(data, i):
    n = data[i]
    i += 1
    if n & 0x80:
        n = ((n & 0x7F) << 8) | data[i]
        i += 1
    return n, i


def _decode_len_utf16(data, i):
    n = struct.unpack_from("<H", data, i)[0]
    i += 2
    if n & 0x8000:
        n2 = struct.unpack_from("<H", data, i)[0]
        i += 2
        n = ((n & 0x7FFF) << 16) | n2
    return n, i


def parse_pool(data, off):
    """Return (strings, info) for the ResStringPool chunk at off."""
    ctype, hsize, csize = struct.unpack_from("<HHI", data, off)
    assert ctype == 0x0001, "not a string pool at %d: 0x%04x" % (off, ctype)
    count, style_count, flags, strings_start, styles_start = struct.unpack_from(
        "<IIIII", data, off + 8)
    utf8 = bool(flags & (1 << 8))
    offsets = struct.unpack_from("<%dI" % count, data, off + hsize)
    strings = []
    for rel in offsets:
        i = off + strings_start + rel
        if utf8:
            u16len, i = _decode_len_utf8(data, i)
            n, i = _decode_len_utf8(data, i) if u16len else (0, i)
            strings.append(data[i:i + n].decode("utf-8", "replace"))
        else:
            n, i = _decode_len_utf16(data, i)
            strings.append(data[i:i + 2 * n].decode("utf-16-le", "replace"))
    styles = data[off + styles_start:off + csize] if style_count else b""
    return strings, dict(header_size=hsize, size=csize, count=count,
                         style_count=style_count, flags=flags, utf8=utf8,
                         styles=styles, styles_start=styles_start)


def build_pool(strings, info):
    """Rebuild a string pool chunk with the same encoding and styles."""
    utf8 = info["utf8"]
    data = bytearray()
    offsets = []
    for s in strings:
        offsets.append(len(data))
        if utf8:
            raw = s.encode("utf-8")
            u16len = len(raw.decode("utf-8"))     # UTF-16 unit count
            n = len(raw)
            for v in (u16len, n) if u16len else (0,):
                if v > 0x7F:
                    data += bytes([0x80 | (v >> 8), v & 0xFF])
                else:
                    data.append(v)
            data += raw + b"\x00"
        else:
            raw = s.encode("utf-16-le")
            n = len(raw) // 2
            if n > 0x7FFF:
                data += struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF)
            else:
                data += struct.pack("<H", n)
            data += raw + b"\x00\x00"
    while len(data) % 4:
        data.append(0)

    count = len(strings)
    style_count = info["style_count"]
    styles = info["styles"]
    hsize = 28
    strings_start = hsize + 4 * count + 4 * style_count
    styles_start = strings_start + len(data) if style_count else 0
    size = strings_start + len(data) + len(styles)
    out = bytearray()
    out += struct.pack("<HHI", 0x0001, hsize, size)
    out += struct.pack("<IIIII", count, style_count, info["flags"],
                       strings_start, styles_start)
    out += struct.pack("<%dI" % count, *offsets)
    if style_count:                     # style offsets are relative, copy as is
        base = info["header_size"] + 4 * info["count"]
        out += info.get("style_offsets_raw", b"")
    out += data
    out += styles
    return bytes(out), offsets


def replace_strings_in_pool(data, pool_off, replacements, drop_sorted=True):
    """Rebuild the pool at pool_off with replacements {index: new_string}."""
    strings, info = parse_pool(data, pool_off)
    for idx, val in replacements.items():
        strings[idx] = val
    # style offsets array has to be preserved verbatim
    if info["style_count"]:
        hsize = info["header_size"]
        info["style_offsets_raw"] = data[pool_off + hsize + 4 * info["count"]:
                                         pool_off + hsize + 4 * info["count"] +
                                         4 * info["style_count"]]
    if drop_sorted:
        info["flags"] &= ~1        # the pool is no longer in sorted order
    new_pool, _ = build_pool(strings, info)
    return new_pool, strings, info


def patch_pool_file(data, pool_off, replacements, total_size_off):
    new_pool, strings, info = replace_strings_in_pool(data, pool_off, replacements)
    old_pool_size = info["size"]
    out = bytearray()
    out += data[:pool_off]
    out += new_pool
    out += data[pool_off + old_pool_size:]
    struct.pack_into("<I", out, total_size_off, len(out))
    return bytes(out), strings


# ------------------------------------------------------------------- manifest
def rename_manifest(data, package=None, version_name=None, label=None):
    strings, info = parse_pool(data, 8)
    repl = {}
    for i, s in enumerate(strings):
        if package and s == package[0]:
            repl[i] = package[1]
        elif version_name and s == version_name[0]:
            repl[i] = version_name[1]
    if not repl:
        raise SystemExit("nothing to replace - strings not found")
    out, _ = patch_pool_file(data, 8, repl, total_size_off=4)
    return out


# ----------------------------------------------------------------- resources
def patch_arsc(data, label_replacements, new_pkg_name):
    """label_replacements: {old_string: new_string}; new_pkg_name or None."""
    ctype, hsize, size, pkg_count = struct.unpack_from("<HHII", data, 0)
    assert ctype == 0x0002, "not a resource table"
    pool_off = hsize
    strings, info = parse_pool(data, pool_off)
    repl = {i: label_replacements[s]
            for i, s in enumerate(strings) if s in label_replacements}
    if repl:
        data, _ = patch_pool_file(data, pool_off, repl, total_size_off=4)
        strings, info = parse_pool(data, pool_off)

    if new_pkg_name:
        # walk chunks after the value pool to find the package chunk (0x0200)
        off = pool_off + info["size"]
        while off < len(data) - 8:
            ctype, chsize, csize = struct.unpack_from("<HHI", data, off)
            if ctype == 0x0200:
                name_off = off + 12          # header(8) + id(4)
                units = new_pkg_name.encode("utf-16-le")
                if len(units) > 256:
                    raise SystemExit("package name too long for arsc field")
                data = bytearray(data)
                data[name_off:name_off + 256] = units.ljust(256, b"\x00")
                data = bytes(data)
                break
            if csize == 0:
                break
            off += csize
    return data


if __name__ == "__main__":
    print("import me")


def _find_package_chunk(data, start):
    off = start
    while off < len(data) - 8:
        ctype, chsize, csize = struct.unpack_from("<HHI", data, off)
        if ctype == 0x0200:
            return off, csize
        if csize == 0:
            break
        off += csize
    raise SystemExit("resource package chunk not found")


def patch_arsc_full(data, label_map=None, path_map=None, key_map=None,
                    new_pkg_name=None):
    """Value-pool strings, resource file paths, resource key names, package name."""
    ctype, hsize, size, pkg_count = struct.unpack_from("<HHII", data, 0)
    assert ctype == 0x0002, "not a resource table"

    # --- global value string pool: labels and file paths -------------------
    pool_off = hsize
    strings, info = parse_pool(data, pool_off)
    repl = {}
    for i, s in enumerate(strings):
        if label_map and s in label_map:
            repl[i] = label_map[s]
        elif path_map and s in path_map:
            repl[i] = path_map[s]
    if repl:
        data, _ = patch_pool_file(data, pool_off, repl, total_size_off=4)
        strings, info = parse_pool(data, pool_off)

    pkg_off, pkg_size = _find_package_chunk(data, pool_off + info["size"])

    # --- resource package name (fixed 128 UTF-16 units) --------------------
    if new_pkg_name:
        units = new_pkg_name.encode("utf-16-le")
        if len(units) > 256:
            raise SystemExit("package name too long for the arsc field")
        data = bytearray(data)
        data[pkg_off + 12:pkg_off + 12 + 256] = units.ljust(256, b"\x00")
        data = bytes(data)

    # --- key string pool: resource entry names -----------------------------
    if key_map:
        key_strings_off = struct.unpack_from("<I", data, pkg_off + 276)[0]
        key_off = pkg_off + key_strings_off
        k_strings, k_info = parse_pool(data, key_off)
        k_repl = {i: key_map[s] for i, s in enumerate(k_strings) if s in key_map}
        if k_repl:
            new_pool, _, _ = replace_strings_in_pool(data, key_off, k_repl)
            delta = len(new_pool) - k_info["size"]
            data = data[:key_off] + new_pool + data[key_off + k_info["size"]:]
            data = bytearray(data)
            struct.pack_into("<I", data, pkg_off + 4, pkg_size + delta)
            struct.pack_into("<I", data, 4, len(data))
            data = bytes(data)
    return data
