# OneUiSansBigClock

A font-swap mod of the ColorOS/OPPO lockscreen "big clock, no colon" font
package. The original clock typeface is replaced with the glyphs from
`OneUISansClockHRd-wght100HEGT700.ttf`, rescaled so the clock keeps the same
size and position on the lockscreen.

| | |
|---|---|
| package | `com.monotype.android.font.oppobigsansnocolon` (unchanged) |
| versionName | `OneUiSansBigClock` |
| minSdk | 34 (Android 14+) |

## Preview

On the lockscreen:

![OneUiSansBigClock on the lockscreen](screenshots/lockscreen.jpg)

Picked from the clock font list, with the weight slider on Thin:

![OneUiSansBigClock in the clock font picker](screenshots/font-picker.jpg)

Outline comparison, original OPPO clock above and OneUiSansBigClock below
(rendered at the same text size):

![Original OPPO clock vs OneUiSansBigClock](preview.png)

## What changed in this build

The base package carried its author's name in several places. All of it is now
gone from the APK payload:

- versionName: `By @<handle> on Telegram` -> `OneUiSansBigClock`
- meta-data value: the `SPDE.env.version` build tag -> `oneuisansbigclock-...`
- resource file names: `res/<author>*.{xml,webp,png}` -> `res/clock*.{xml,webp,png}`
- resource key names: `drawable/<author>*` -> `drawable/clock*`
- app labels: `Lockscreen OPPO Big Clock...` -> `OneUiSansBigClock`, in English
  and all three Chinese variants

The build script re-checks every entry of the finished APK for the string and
reports none. Credit for the base package is given in
[Credits](#credits), which is the only place the name still appears.

The clock font itself is byte-identical to the earlier build of this package -
only names changed.

## Package layout

```
OneUiSansBigClock.apk       the signed, ready-to-install result
preview.png                 outline comparison render
screenshots/                lockscreen and font-picker screenshots

source-apk/                 the pristine original APK (build input)
                            Untouched base exactly as published, so it still
                            carries the original author's resource file names -
                            that is what makes it usable as a base. Everything
                            this build produces (the APK, modified/, the
                            scripts) has no author branding; the credit is in
                            Credits below.

modified/                   the four files that differ from the original
  AndroidManifest.xml                            versionName, build tag
  resources.arsc                                 labels, paths, keys
  assets/fonts/LOCKSCREENOPPOBigClockNoColon.ttf rebuilt clock font
  assets/xml/LOCKSCREENOPPOBigClockNoColon.xml   display name

build/
  build_font.py             builds the new TTF from the base + your font
  build_apk.py              assembles the APK, renames and strips the name
  apkpatch.py               binary XML / arsc string-pool rewriter
  keystore.jks              throwaway signing key (see Signing below)

fonts/
  OneUISansClockHRd-wght100HEGT700.ttf   the source font
```

The name `OneUiSansBigClock` is used everywhere it can be: the font list entry
(`assets/xml` displayname), the app label, the versionName and the font's own
family / PostScript name inside the TTF.

## How the font swap works

The slot font is a digits-only face: 13 glyphs (`.notdef`, space, 0-9, colon).
Both fonts share that glyph set, so it is a straight outline replacement. Three
numbers were carried over from the original so the clock does not move or
change size:

- **digit advance width** 767 units per 1000 em, identical, so `12 34` occupies
  exactly the same width as before
- **ink band centre** the OneUI outlines are scaled uniformly by 1.4864 and
  shifted down 844 units, so their vertical centre sits where the original
  digits' centre was
- **line metrics** `hhea` and `OS/2` ascent 700 / descent -3540, winAscent 700 /
  winDescent 3540, copied verbatim

Consequence: because the OneUI digits are proportionally wider than the OPPO
ones, holding the width fixed makes the letterforms about 20% shorter in height
than the original clock. Still large, just slightly less tall. Matching the
original height instead would make the clock about 25% wider than the original
and risks clipping at the screen edges. To build that variant, replace the
advance-matching scale `k = o_adv / src_adv` in `build_font.py` with a
height-matching scale, i.e. the ratio of the two fonts' digit ink heights.

The colon glyph is kept empty with a 10-unit advance, preserving the "NoColon"
behaviour; `.notdef` is copied from the original so any unexpected character
still renders as before.

Tables dropped from the new font: `vhea`, `vmtx`, `DSIG` (the original slot had
none of them). Everything else is inherited from the OneUI file. The writer
keeps the base font's `head` timestamp, so rebuilds are byte-identical.

## Rebuilding from scratch

Both scripts work in place, no path editing needed - they resolve everything
relative to this folder. You need fontTools (`pip install fonttools`) plus a JDK
and Android build-tools for the signing step.

```sh
python3 build/build_font.py
#   reads source-apk/ + fonts/, writes build/newclock.ttf, prints a per-digit
#   comparison of advances and ink boxes plus a metric consistency check

python3 build/build_apk.py
#   writes build/unsigned.apk from source-apk/, substituting modified/,
#   renaming the resources, dropping META-INF and checking the result for the
#   author name

zipalign -p -f 4 build/unsigned.apk build/aligned.apk
apksigner sign --ks build/keystore.jks --ks-pass pass:android \
    --key-pass pass:android --min-sdk-version 21 \
    --v1-signing-enabled false --v2-signing-enabled true \
    --v3-signing-enabled true --out OneUiSansBigClock.apk \
    build/aligned.apk
```

To change the font, drop your TTF in `fonts/` and point `SRC` in
`build_font.py` at it (or keep the same filename). The script only needs digits
0-9, colon and space, all in a 1000-unit em; anything else is ignored.

## How the rename works

`AndroidManifest.xml` and `resources.arsc` are binary chunk files whose strings
live in string pools. Attribute and resource values reference strings by index,
never by offset, so `apkpatch.py` rebuilds the affected pools and leaves every
node untouched - only the file's total size and the enclosing chunk sizes
change. Both files were checked with `aapt2` afterwards: versionName, all four
labels and all four drawable names read back correctly and the resource table
resolves.

## Credits

- **Base package** - the original "OPPO Big Clock, no colon" lockscreen font
  module for ColorOS, as built and published by **HeheJuice**
  ([@HeheJuice](https://t.me/HeheJuice) on Telegram). This mod only replaces the
  clock typeface and renames the internals; the module structure, resources,
  SEC-INF build artefacts and the OPPO font slot itself are their work.
- **TTF fixing** - **@Alizabp** ([@Alizabp](https://t.me/Alizabp) on Telegram),
  for fixing the TTF file.

## Signing

The original OPPO signature cannot be reproduced, so the APK is re-signed with a
self-signed key. `keystore.jks` is that key: alias `clockfont`, store and key
password `android`. It is a throwaway key generated for this build - keep it if
you want to ship updates that install over the top, but do not use it for
anything you care about. Because the signature differs from the original, the
old package must be uninstalled before installing this one.

## Notes

- Package name and version code are unchanged
  (`com.monotype.android.font.oppobigsansnocolon`, versionCode 200000001), so
  this replaces the stock pack rather than sitting beside it.
- minSdkVersion is 34, i.e. Android 14+, same as the original.
- `SEC-INF/` is left untouched. It carries an OPPO build digest that no longer
  matches the modified payload; it cannot be regenerated, and on installs that
  enforce it the module may be ignored. It is also the one place an author
  string could still exist, in encrypted form.
- The supplied font is a weight-100 instance, so the clock reads as a thin
  hairline style.
