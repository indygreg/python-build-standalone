#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/deps/bin:${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

tar -xf tk${TK_VERSION}-src.tar.gz

pushd tk${TK_VERSION}

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    # The @available annotations create missing symbol errors
    # for ___isOSVersionAtLeast. We work around this by removing
    # their use.
    #
    # This is not an ideal solution.
    patch -p1 << EOF
diff --git a/macosx/tkMacOSXColor.c b/macosx/tkMacOSXColor.c
index 80b368f..b51796e 100644
--- a/macosx/tkMacOSXColor.c
+++ b/macosx/tkMacOSXColor.c
@@ -278,11 +278,9 @@ SetCGColorComponents(
     OSStatus err = noErr;
     NSColor *bgColor, *color = nil;
     CGFloat rgba[4] = {0, 0, 0, 1};
-#if MAC_OS_X_VERSION_MAX_ALLOWED < 101400
     NSInteger colorVariant;
     static CGFloat graphiteAccentRGBA[4] =
 	{152.0 / 255, 152.0 / 255, 152.0 / 255, 1.0};
-#endif
 
     if (!deviceRGB) {
 	deviceRGB = [NSColorSpace deviceRGBColorSpace];
@@ -373,16 +371,6 @@ SetCGColorComponents(
 			  deviceRGB];
 	    break;
 	case 8:
-#if MAC_OS_X_VERSION_MAX_ALLOWED >= 101400
-	    if (@available(macOS 10.14, *)) {
-		color = [[NSColor controlAccentColor] colorUsingColorSpace:
-							  deviceRGB];
-	    } else {
-		color = [NSColor colorWithColorSpace: deviceRGB
-				 components: blueAccentRGBA
-				 count: 4];
-	    }
-#else
 	    colorVariant = [[NSUserDefaults standardUserDefaults]
 			       integerForKey:@"AppleAquaColorVariant"];
 	    if (colorVariant == 6) {
@@ -394,7 +382,6 @@ SetCGColorComponents(
 				 components: blueAccentRGBA
 				 count: 4];
 	    }
-#endif
 	    break;
 	default:
 #if MAC_OS_X_VERSION_MAX_ALLOWED >= 101000
diff --git a/macosx/tkMacOSXWm.c b/macosx/tkMacOSXWm.c
index ceb3f3f..5c04f17 100644
--- a/macosx/tkMacOSXWm.c
+++ b/macosx/tkMacOSXWm.c
@@ -5928,12 +5928,6 @@ WmWinAppearance(
 	    resultString = appearanceStrings[APPEARANCE_AUTO];
 	} else if (appearance == NSAppearanceNameAqua) {
 	    resultString = appearanceStrings[APPEARANCE_AQUA];
-#if MAC_OS_X_VERSION_MAX_ALLOWED >= 101400
-	} else if (@available(macOS 10.14, *)) {
-	    if (appearance == NSAppearanceNameDarkAqua) {
-		resultString = appearanceStrings[APPEARANCE_DARKAQUA];
-	    }
-#endif // MAC_OS_X_VERSION_MAX_ALLOWED >= 101400
 	}
 	result = Tcl_NewStringObj(resultString, strlen(resultString));
     }
@@ -5953,12 +5947,6 @@ WmWinAppearance(
 		NSAppearanceNameAqua];
 	    break;
 	case APPEARANCE_DARKAQUA:
-#if MAC_OS_X_VERSION_MAX_ALLOWED >= 101400
-	    if (@available(macOS 10.14, *)) {
-		win.appearance = [NSAppearance appearanceNamed:
-		    NSAppearanceNameDarkAqua];
-	    }
-#endif // MAC_OS_X_VERSION_MAX_ALLOWED >= 101400
 	    break;
 	default:
 	    win.appearance = nil;
EOF
fi

pushd unix

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"
LDFLAGS=""

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/include -Wno-availability"
    CFLAGS="${CFLAGS} -Wno-deprecated-declarations -Wno-unknown-attributes -Wno-typedef-redefinition"
    LDFLAGS="-L${TOOLS_PATH}/deps/lib"
    EXTRA_CONFIGURE_FLAGS="--enable-aqua=yes --without-x"
else
    EXTRA_CONFIGURE_FLAGS="--x-includes=${TOOLS_PATH}/deps/include --x-libraries=${TOOLS_PATH}/deps/lib"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-tcl=${TOOLS_PATH}/deps/lib \
    --enable-shared=no \
    --enable-threads \
    ${EXTRA_CONFIGURE_FLAGS}

# For some reason musl isn't link libXau and libxcb. So we hack the Makefile
# to do what we want.
#
# In addition, the wish binary is also failing to link. So we remove it
# from the build and the installation (it shouldn't be needed anyway).
if [ "${CC}" = "musl-clang" ]; then
    sed -i 's/-ldl  -lpthread /-ldl  -lpthread -lXau -lxcb/' tkConfig.sh
    sed -i 's/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread -lXau -lxcb/' Makefile
    sed -i 's/all: binaries libraries doc/all: libraries/' Makefile
    sed -i 's/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE) ${WISH_EXE}/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE)/' Makefile
fi

make -j ${NUM_CPUS}
touch wish
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

# For some reason libtk*.a have weird permissions. Fix that.
chmod 644 /${ROOT}/out/tools/deps/lib/libtk*.a

rm ${ROOT}/out/tools/deps/bin/wish*
