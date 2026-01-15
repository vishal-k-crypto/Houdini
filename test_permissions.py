#!/usr/bin/env python3
"""
Test macOS permissions required for Houdini Agent.

This script verifies:
1. Accessibility permissions (read UI from other apps)
2. Screen Recording permissions (capture screenshots)
3. Coordinate system (Retina display handling)
4. App focus detection (can detect when new app opens)

Run this FIRST if agent is stuck in Terminal or clicking wrong places.
"""

import sys
import time


def test_pyobjc():
    """Test that PyObjC is installed and working."""
    print("\n" + "=" * 60)
    print("TEST 1: PyObjC Installation")
    print("=" * 60)
    
    try:
        from Cocoa import NSWorkspace, NSScreen
        from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        print("✅ PyObjC frameworks imported successfully")
        return True
    except ImportError as e:
        print(f"❌ PyObjC import failed: {e}")
        print("\n   FIX: pip install pyobjc pyobjc-framework-Quartz pyobjc-framework-ApplicationServices")
        return False


def test_frontmost_app():
    """Test that we can detect the frontmost application."""
    print("\n" + "=" * 60)
    print("TEST 2: Frontmost App Detection")
    print("=" * 60)
    
    try:
        from Cocoa import NSWorkspace
        
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication()
        
        if app:
            name = app.localizedName()
            bundle_id = app.bundleIdentifier()
            print(f"✅ Frontmost app: {name} ({bundle_id})")
            return True
        else:
            print("❌ Could not get frontmost application")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_accessibility():
    """Test Accessibility API permissions."""
    print("\n" + "=" * 60)
    print("TEST 3: Accessibility Permissions")
    print("=" * 60)
    
    try:
        from ApplicationServices import (
            AXUIElementCreateSystemWide,
            AXUIElementCopyAttributeValue,
            AXIsProcessTrusted
        )
        from CoreFoundation import CFRelease
        
        # Check if process is trusted for accessibility
        is_trusted = AXIsProcessTrusted()
        
        if is_trusted:
            print("✅ Process is trusted for Accessibility")
        else:
            print("❌ Process is NOT trusted for Accessibility")
            print("\n   FIX: System Settings > Privacy & Security > Accessibility")
            print("        Add your terminal app (Terminal/iTerm/VS Code) and ENABLE it")
            print("        Then RESTART your terminal!")
            return False
        
        # Try to actually read the system-wide element
        system_wide = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(system_wide, "AXFocusedApplication", None)
        
        if err == 0 and focused:
            print("✅ Can read AXFocusedApplication from system")
            return True
        else:
            print(f"⚠️  AXFocusedApplication returned error code: {err}")
            print("   This might still work - trying alternative method...")
            
            # Try reading from frontmost app
            from Cocoa import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app:
                from ApplicationServices import AXUIElementCreateApplication
                app_ref = AXUIElementCreateApplication(app.processIdentifier())
                err2, windows = AXUIElementCopyAttributeValue(app_ref, "AXWindows", None)
                if err2 == 0:
                    print(f"✅ Can read UI elements from {app.localizedName()}")
                    return True
            
            print("❌ Cannot read accessibility attributes")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_screen_recording():
    """Test Screen Recording permissions via window list."""
    print("\n" + "=" * 60)
    print("TEST 4: Screen Recording Permissions")
    print("=" * 60)
    
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        if window_list is None:
            print("❌ Cannot get window list - Screen Recording permission needed")
            print("\n   FIX: System Settings > Privacy & Security > Screen Recording")
            print("        Add your terminal app and ENABLE it")
            print("        Then RESTART your terminal!")
            return False
        
        # Check if we can see window names (not just our own windows)
        other_app_windows = 0
        our_pid = None
        
        import os
        our_pid = os.getpid()
        
        for window in window_list:
            owner_pid = window.get("kCGWindowOwnerPID", 0)
            owner_name = window.get("kCGWindowOwnerName", "")
            window_name = window.get("kCGWindowName", "")
            
            if owner_pid != our_pid and owner_name:
                other_app_windows += 1
                if other_app_windows == 1:
                    print(f"   Sample window: {owner_name} - '{window_name}'")
        
        if other_app_windows > 0:
            print(f"✅ Can see {other_app_windows} windows from other apps")
            return True
        else:
            print("⚠️  Can only see our own windows - might need Screen Recording permission")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_screen_coordinates():
    """Test screen coordinate handling for Retina displays."""
    print("\n" + "=" * 60)
    print("TEST 5: Screen Coordinates (Retina)")
    print("=" * 60)
    
    try:
        from Cocoa import NSScreen
        from Quartz import CGDisplayBounds, CGMainDisplayID
        
        # Get main screen
        main_screen = NSScreen.mainScreen()
        frame = main_screen.frame()
        
        # NSScreen gives logical (point) coordinates
        ns_width = frame.size.width
        ns_height = frame.size.height
        
        # CGDisplayBounds gives native (pixel) coordinates
        display_id = CGMainDisplayID()
        cg_bounds = CGDisplayBounds(display_id)
        cg_width = cg_bounds.size.width
        cg_height = cg_bounds.size.height
        
        # Calculate scale factor
        scale_x = cg_width / ns_width if ns_width else 1
        scale_y = cg_height / ns_height if ns_height else 1
        
        print(f"   NSScreen (logical):  {int(ns_width)} x {int(ns_height)}")
        print(f"   CGDisplay (native):  {int(cg_width)} x {int(cg_height)}")
        print(f"   Scale factor: {scale_x:.1f}x")
        
        # PyAutoGUI should match NSScreen
        try:
            import pyautogui
            pag_size = pyautogui.size()
            print(f"   PyAutoGUI:           {pag_size.width} x {pag_size.height}")
            
            if pag_size.width == int(ns_width) and pag_size.height == int(ns_height):
                print("✅ PyAutoGUI matches NSScreen (correct!)")
                return True
            else:
                print("⚠️  PyAutoGUI doesn't match NSScreen - coordinate issues possible")
                return False
        except ImportError:
            print("⚠️  PyAutoGUI not installed - skipping coordinate check")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_ui_element_reading():
    """Test reading UI elements from an app."""
    print("\n" + "=" * 60)
    print("TEST 6: UI Element Reading")
    print("=" * 60)
    
    try:
        from Cocoa import NSWorkspace
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            AXUIElementCopyAttributeNames
        )
        
        # Get frontmost app
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication()
        
        if not app:
            print("❌ No frontmost app")
            return False
        
        app_name = app.localizedName()
        pid = app.processIdentifier()
        
        # Create AX element for the app
        app_ref = AXUIElementCreateApplication(pid)
        
        # Try to get attribute names
        err, attrs = AXUIElementCopyAttributeNames(app_ref, None)
        
        if err != 0:
            print(f"❌ Cannot read attributes from {app_name} (error: {err})")
            print("   This usually means Accessibility permission is not granted")
            return False
        
        print(f"   Reading from: {app_name}")
        print(f"   Available attributes: {len(attrs)}")
        
        # Try to get windows
        err, windows = AXUIElementCopyAttributeValue(app_ref, "AXWindows", None)
        
        if err == 0 and windows:
            print(f"   Windows found: {len(windows)}")
            
            # Try to get first window's children
            if len(windows) > 0:
                window = windows[0]
                err, children = AXUIElementCopyAttributeValue(window, "AXChildren", None)
                if err == 0 and children:
                    print(f"   First window children: {len(children)}")
                    print("✅ Can read UI hierarchy")
                    return True
        
        print("✅ Can read app attributes (no windows currently open)")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all permission tests."""
    print("\n" + "=" * 60)
    print("  HOUDINI AGENT PERMISSION CHECK")
    print("=" * 60)
    
    results = {}
    
    # Run tests
    results["PyObjC"] = test_pyobjc()
    
    if results["PyObjC"]:
        results["Frontmost App"] = test_frontmost_app()
        results["Accessibility"] = test_accessibility()
        results["Screen Recording"] = test_screen_recording()
        results["Coordinates"] = test_screen_coordinates()
        results["UI Elements"] = test_ui_element_reading()
    
    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("🎉 All tests passed! Houdini Agent should work correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        print("\nQuick fix steps:")
        print("1. Open System Settings > Privacy & Security")
        print("2. Grant Accessibility permission to your terminal")
        print("3. Grant Screen Recording permission to your terminal")
        print("4. RESTART your terminal completely")
        print("5. Run this test again")
        return 1


if __name__ == "__main__":
    sys.exit(main())
