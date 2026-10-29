"""Assemble the OneUI Sans clock package, with every base-author reference gone.

The package name is deliberately left as the original
com.monotype.android.font.oppobigsansnocolon so this build replaces the stock
OPPO pack instead of sitting next to it.
"""
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apkpatch as ap

PKG = os.path.dirname(HERE)
SRC_APK = os.path.join(PKG, "source-apk", "OPPOBigClockSansNoColon.apk")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "unsigned.apk")
FONT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    PKG, "modified", "assets", "fonts", "LOCKSCREENOPPOBigClockNoColon.ttf")

NEW_VER = "OneUiSansBigClock"
NEW_TAG = "oneuisansbigclock-300000-3.0.00"

LABELS = {
    "Lockscreen OPPO Big Clock No Colon Font Set ": "OneUiSansBigClock",
    "锁屏OPPO大时钟无冒号字体": "OneUiSansBigClock",
    "鎖定螢幕OPPO大時鐘無冒號字體": "OneUiSansBigClock",
}

# the four preview images are found by shape - res/<anything>Icon.xml,
# <anything>Back.webp, <anything>Front.png, <anything>Mono.png - so this script
# carries no author branding of its own
IMAGE = re.compile(r"^res/[^/]*?(Icon|Back|Front|Mono)\.(xml|webp|png)$")


def image_maps(names):
    paths, keys, stems = {}, {}, set()
    for n in names:
        m = IMAGE.match(n)
        if not m:
            continue
        part, ext = m.group(1).lower(), m.group(2)
        stem = n[len("res/"):-(len(ext) + 1)]
        stems.add(stem)
        paths[n] = "res/clock%s.%s" % (part, ext)
        keys[stem] = "clock%s" % part
    return paths, keys, stems

# strings to neutralise are found by shape, not by name: the versionName is the
# one carrying an @handle, the build tag is the OPPO <n>/<n>/release/<name> one
HANDLE = re.compile(r"@\w{3,}")
BUILD_TAG = re.compile(r"^(\d+/\d+/release/)[^/]+$")

CLOCK_XML = """<?xml version="1.0" encoding="utf-8"?>
<font displayname="OneUiSansBigClock">
\t<sans>
\t\t<file>
\t\t\t<filename>LOCKSCREENOPPOBigClockNoColon.ttf</filename>
\t\t\t<droidname>DroidSans.ttf</droidname>
\t\t</file>
\t\t<file>
\t\t\t<filename>LOCKSCREENOPPOBigClockNoColon.ttf</filename>
\t\t\t<droidname>DroidSans-Bold.ttf</droidname>
\t\t</file>
\t</sans>
</font>
"""

FONT_ENTRY = "assets/fonts/LOCKSCREENOPPOBigClockNoColon.ttf"
XML_ENTRY = "assets/xml/LOCKSCREENOPPOBigClockNoColon.xml"
DROP = {"META-INF/MANIFEST.MF", "META-INF/ANDROID.SF", "META-INF/ANDROID.RSA"}


def main():
    zin = zipfile.ZipFile(SRC_APK)

    man = zin.read("AndroidManifest.xml")
    strings, _ = ap.parse_pool(man, 8)
    repl = {}
    for i, s in enumerate(strings):
        if HANDLE.search(s):
            repl[i] = NEW_VER
        else:
            m = BUILD_TAG.match(s)
            if m:
                repl[i] = m.group(1) + NEW_TAG
    if not repl:
        raise SystemExit("no versionName / build tag found to neutralise")
    man, _ = ap.patch_pool_file(man, 8, repl, total_size_off=4)
    print("neutralised strings:", sorted(repl.values()))

    PATHS, KEYS, STEMS = image_maps(zin.namelist())
    arsc = ap.patch_arsc_full(zin.read("resources.arsc"), label_map=LABELS,
                              path_map=PATHS, key_map=KEYS)

    font = open(FONT, "rb").read()

    with zipfile.ZipFile(OUT, "w") as zout:
        for info in zin.infolist():
            if info.filename in DROP:
                continue
            name = PATHS.get(info.filename, info.filename)
            if info.filename == "AndroidManifest.xml":
                data = man
            elif info.filename == "resources.arsc":
                data = arsc
            elif info.filename == FONT_ENTRY:
                data = font
            elif info.filename == XML_ENTRY:
                data = CLOCK_XML.encode("utf-8")
            else:
                data = zin.read(info.filename)
            zi = zipfile.ZipInfo(name, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zout.writestr(zi, data)

    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))
    print("versionName:", NEW_VER, "| package unchanged")

    z = zipfile.ZipFile(OUT)
    hits = []
    for entry in z.namelist():
        for stem in STEMS:
            raw = stem.encode()
            if stem in entry or raw in z.read(entry) or stem.lower() in entry.lower():
                hits.append(entry)
                break
    print("remaining base-author references:", sorted(set(hits)) if hits else "none")


if __name__ == "__main__":
    main()
