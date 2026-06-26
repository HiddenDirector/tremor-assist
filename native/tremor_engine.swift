// Native macOS event-tap engine for TremorAssist.
//
// Owns a CGEventTap and its CFRunLoop on a dedicated thread and runs the One
// Euro Filter + dead-zone (from the C core) inline in the tap callback. Mouse
// motion is smoothed entirely in compiled code: the per-event path never enters
// the Python interpreter and never takes the GIL, which is what removes the
// micro-stutter you feel in games when the filter runs in Python.
//
// Python drives it over a small C ABI (see the @_cdecl exports at the bottom)
// via ctypes; it only calls in to start/stop/configure and to read counters.

import CoreGraphics
import Foundation

private final class NativeEngine {
    static let shared = NativeEngine()

    private var filter: OpaquePointer?
    private var deadzone: OpaquePointer?
    private var tap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var thread: Thread?
    private var runLoop: CFRunLoop?

    private(set) var eventsSmoothed: UInt64 = 0
    private let lock = NSLock()

    // Live parameters, read on the tap thread.
    var minCutoff: Double = 1.0
    var beta: Double = 0.02
    var dCutoff: Double = 1.0
    var deadzonePx: Double = 1.5
    var enabled: Bool = true

    func configure(minCutoff: Double, beta: Double, dCutoff: Double, deadzonePx: Double) {
        lock.lock()
        self.minCutoff = minCutoff
        self.beta = beta
        self.dCutoff = dCutoff
        self.deadzonePx = deadzonePx
        if let f = filter {
            te_oneeuro2d_update_params(f, minCutoff, beta, dCutoff)
        }
        if let d = deadzone {
            te_deadzone_set_radius(d, deadzonePx)
        }
        lock.unlock()
    }

    func setEnabled(_ on: Bool) {
        lock.lock()
        enabled = on
        if let f = filter { te_oneeuro2d_reset(f) }
        if let d = deadzone { te_deadzone_reset(d, 0, 0, 0) }
        lock.unlock()
    }

    // Called from the C tap callback for each mouse-move/drag event.
    func handleMove(_ event: CGEvent) {
        lock.lock()
        let on = enabled
        lock.unlock()
        guard on, let f = filter, let d = deadzone else { return }

        let p = event.location
        let ts = Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000_000.0

        var sx = 0.0, sy = 0.0
        te_oneeuro2d_filter(f, Double(p.x), Double(p.y), ts, &sx, &sy)
        var hx = 0.0, hy = 0.0
        te_deadzone_apply(d, sx, sy, &hx, &hy)

        event.location = CGPoint(x: hx, y: hy)
        lock.lock()
        eventsSmoothed &+= 1
        lock.unlock()
    }

    func start() -> Int32 {
        if tap != nil { return 0 }

        filter = te_oneeuro2d_new(minCutoff, beta, dCutoff)
        deadzone = te_deadzone_new(deadzonePx)

        let mask: CGEventMask =
            (1 << CGEventType.mouseMoved.rawValue) |
            (1 << CGEventType.leftMouseDragged.rawValue) |
            (1 << CGEventType.rightMouseDragged.rawValue) |
            (1 << CGEventType.otherMouseDragged.rawValue)

        let callback: CGEventTapCallBack = { _, type, event, _ in
            switch type {
            case .mouseMoved, .leftMouseDragged, .rightMouseDragged, .otherMouseDragged:
                NativeEngine.shared.handleMove(event)
            case .tapDisabledByTimeout, .tapDisabledByUserInput:
                if let t = NativeEngine.shared.tap {
                    CGEvent.tapEnable(tap: t, enable: true)
                }
            default:
                break
            }
            return Unmanaged.passUnretained(event)
        }

        guard let port = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: mask,
            callback: callback,
            userInfo: nil
        ) else {
            // Most commonly: Accessibility permission not granted.
            return -1
        }
        tap = port

        let t = Thread {
            self.runLoop = CFRunLoopGetCurrent()
            self.runLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, port, 0)
            CFRunLoopAddSource(CFRunLoopGetCurrent(), self.runLoopSource, .commonModes)
            CGEvent.tapEnable(tap: port, enable: true)
            CFRunLoopRun()
        }
        t.name = "tremor.eventtap"
        t.qualityOfService = .userInteractive
        thread = t
        t.start()
        return 0
    }

    func stop() {
        if let port = tap {
            CGEvent.tapEnable(tap: port, enable: false)
        }
        if let rl = runLoop {
            CFRunLoopStop(rl)
        }
        tap = nil
        runLoopSource = nil
        thread = nil
        runLoop = nil
        if let f = filter { te_oneeuro2d_free(f); filter = nil }
        if let d = deadzone { te_deadzone_free(d); deadzone = nil }
    }
}

@_cdecl("te_engine_start")
public func te_engine_start() -> Int32 {
    return NativeEngine.shared.start()
}

@_cdecl("te_engine_stop")
public func te_engine_stop() {
    NativeEngine.shared.stop()
}

@_cdecl("te_engine_configure")
public func te_engine_configure(_ minCutoff: Double, _ beta: Double,
                                _ dCutoff: Double, _ deadzonePx: Double) {
    NativeEngine.shared.configure(minCutoff: minCutoff, beta: beta,
                                  dCutoff: dCutoff, deadzonePx: deadzonePx)
}

@_cdecl("te_engine_set_enabled")
public func te_engine_set_enabled(_ on: Int32) {
    NativeEngine.shared.setEnabled(on != 0)
}

@_cdecl("te_engine_events_smoothed")
public func te_engine_events_smoothed() -> UInt64 {
    return NativeEngine.shared.eventsSmoothed
}
