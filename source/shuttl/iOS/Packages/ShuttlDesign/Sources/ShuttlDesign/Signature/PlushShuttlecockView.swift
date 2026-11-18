#if canImport(UIKit)
import SwiftUI
import SceneKit
import UIKit
import os

// MARK: - PlushShuttlecockView
// The plush shuttlecock as something to handle. A finger on it squeezes it; dragging spins
// and tips it, and the fur lies down under the finger and springs back; letting go lets it
// bounce out. Flicking it upward counts as a tap: that is how a shuttle is served.
//
// What it means is the owner's business. This view shows four things on request: how fluffed
// up it is, whether it is hopping to be picked, a shake of the head, and being served (it
// winds up to fly; the owner moves the view, and it lands when `served` goes back).

public struct PlushShuttlecockView: UIViewRepresentable {
    /// 0 = fur short and lying down, 1 = fully fluffed up.
    public var fluff: Double
    /// Hops in place, asking to be served.
    public var eager: Bool
    /// Each increase shakes its head once.
    public var refusals: Int
    /// Winds up and spins when this turns on; squashes on landing when it turns off.
    public var served: Bool
    public var onTap: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(fluff: Double, eager: Bool = false, refusals: Int = 0, served: Bool = false,
                onTap: @escaping () -> Void = {}) {
        self.fluff = fluff
        self.eager = eager
        self.refusals = refusals
        self.served = served
        self.onTap = onTap
    }

    public func makeCoordinator() -> PlushHandler { PlushHandler() }

    public func makeUIView(context: Context) -> PlushStage {
        context.coordinator.makeStage()
    }

    public func updateUIView(_ stage: PlushStage, context: Context) {
        context.coordinator.show(fluff: Float(fluff), eager: eager, still: reduceMotion,
                                 refusals: refusals, served: served, onTap: onTap)
    }

    public static func dismantleUIView(_ stage: PlushStage, coordinator: PlushHandler) {
        coordinator.stop()
    }
}

// MARK: - PlushStage
// Holds the scene view at a whole number of points, whatever size the layout hands down, and
// reports when a finger goes down on it and comes up.
//
// SceneKit presents no frames at all at some fractional sizes: on a 3x screen a view two
// thirds of a point over a whole number (337.67 pt, 321.67 pt) stayed empty, while whole
// points and one third over drew normally. A SwiftUI frame such as "84 % of the width" lands
// on those sizes on some phones and not others, so the scene view is never given one.

public final class PlushStage: UIView {
    private let scene: SCNView
    var onHold: (Bool) -> Void = { _ in }

    init(scene: SCNView) {
        self.scene = scene
        super.init(frame: .zero)
        backgroundColor = .clear
        // Touches belong to the stage; the scene only draws.
        scene.isUserInteractionEnabled = false
        addSubview(scene)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    public override func layoutSubviews() {
        super.layoutSubviews()
        scene.frame = CGRect(x: 0, y: 0, width: floor(bounds.width), height: floor(bounds.height))
    }

    public override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesBegan(touches, with: event)
        onHold(true)
    }

    public override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesEnded(touches, with: event)
        onHold(false)
    }

    public override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesCancelled(touches, with: event)
        onHold(false)
    }
}

// MARK: - PlushHandler
// The main-thread half: builds the stage, turns touches into wishes for the motion, and
// plays the haptics. Nothing here moves the model.

@MainActor
public final class PlushHandler: NSObject {
    private let motion = PlushMotion()
    private weak var stage: PlushStage?
    private var onTap: () -> Void = {}
    private var refusalsShown = 0
    /// nil until the first `show`: how the view starts out is a state, not an event.
    private var wasServed: Bool?
    /// Finger travel since the last tick of haptic, in points.
    private var stroked: CGFloat = 0
    private let fur = UIImpactFeedbackGenerator(style: .soft)
    private let racket = UIImpactFeedbackGenerator(style: .rigid)

    func makeStage() -> PlushStage {
        let view = SCNView()
        view.scene = motion.toy.scene
        view.pointOfView = motion.toy.camera
        view.delegate = motion
        view.backgroundColor = .clear
        view.isOpaque = false
        view.antialiasingMode = .multisampling4X
        view.autoenablesDefaultLighting = false
        view.preferredFramesPerSecond = 60
        view.rendersContinuously = true

        let stage = PlushStage(scene: view)
        stage.onHold = { [weak self] down in self?.held(down) }
        // The stage hears the finger come up even when a drag or a tap is recognised.
        let pan = UIPanGestureRecognizer(target: self, action: #selector(panned(_:)))
        pan.cancelsTouchesInView = false
        let tap = UITapGestureRecognizer(target: self, action: #selector(tapped))
        tap.cancelsTouchesInView = false
        stage.addGestureRecognizer(pan)
        stage.addGestureRecognizer(tap)
        self.stage = stage
        return stage
    }

    func stop() {
        stage?.onHold = { _ in }
    }

    func show(fluff: Float, eager: Bool, still: Bool, refusals: Int, served: Bool, onTap: @escaping () -> Void) {
        self.onTap = onTap
        let shake = refusals > refusalsShown
        refusalsShown = refusals
        let launch = served && wasServed == false
        let land = !served && wasServed == true
        wasServed = served
        if launch { racket.impactOccurred(intensity: 1) }
        motion.change { wishes in
            wishes.fluff = fluff
            wishes.eager = eager
            wishes.still = still
            if shake { wishes.shake = true }
            if launch { wishes.launch = true }
            if land { wishes.land = true }
        }
    }

    // MARK: Touch

    private func held(_ down: Bool) {
        if down { fur.impactOccurred(intensity: 0.55) }
        motion.change { $0.held = down }
    }

    @objc private func tapped() {
        fur.impactOccurred(intensity: 0.9)
        motion.change { $0.squeeze += 2.5 }
        onTap()
    }

    @objc private func panned(_ pan: UIPanGestureRecognizer) {
        guard let stage else { return }
        let move = pan.translation(in: stage)
        pan.setTranslation(.zero, in: stage)
        // Points to radians: a swipe across the stage is about one turn.
        let turn: Float = 2 * .pi / Float(max(stage.bounds.width, 1))
        let dx = Float(move.x), dy = Float(move.y)

        switch pan.state {
        case .changed:
            motion.change { wishes in
                wishes.turn += dx * turn
                // Dragging down tips the top toward you.
                wishes.tilt += dy * turn * 0.45
                // The pile goes the way the finger goes (screen y runs down, the world's up).
                wishes.stroke += simd_float3(dx, -dy, 0) * 0.02
            }
            stroked += abs(move.x) + abs(move.y)
            if stroked > 26 {
                stroked = 0
                fur.impactOccurred(intensity: 0.45)
            }
        case .ended:
            let velocity = pan.velocity(in: stage)
            if velocity.y < -900 && abs(velocity.y) > abs(velocity.x) * 1.5 {
                // Flicked upward: a serve.
                tapped()
            } else {
                let spin = Float(velocity.x) * turn
                motion.change { $0.spin = spin }
            }
        default:
            break
        }
    }
}

// MARK: - PlushMotion
// The render-thread half: owns the model and steps its small physics exactly once per frame
// drawn, just before SceneKit draws it. Stepping anywhere else (a timer, the main thread's
// own display link) runs out of phase with the frames and shows as a faint stutter.
//
// The main thread never touches the model. It leaves wishes under a lock; each frame takes
// them, and the one-shot ones (a nudge, a release, a shake) are cleared as they are taken.

final class PlushMotion: NSObject, SCNSceneRendererDelegate, @unchecked Sendable {
    let toy = PlushShuttlecock()

    struct Wishes: Sendable {
        var fluff: Float = 0.3
        var eager = false
        var still = false
        /// A finger is down on it.
        var held = false
        // One-shots since the last frame.
        var turn: Float = 0
        var tilt: Float = 0
        var stroke = simd_float3(repeating: 0)
        var spin: Float?
        var squeeze: Float = 0
        var shake = false
        var launch = false
        var land = false
    }

    private let wishes = OSAllocatedUnfairLock(initialState: Wishes())

    func change(_ body: @Sendable (inout Wishes) -> Void) {
        wishes.withLock(body)
    }

    // Everything below belongs to the render thread.
    private var last: TimeInterval = 0
    private var clock: Float = 0
    private var fluff: Float = 0.3
    private var fluffSpeed: Float = 0
    /// Turn about the toy's own axis, and how fast it is turning.
    private var yaw: Float = 0.5
    private var spin: Float = 0
    /// How far it is tipped toward or away from the viewer.
    private var pitch: Float = 0
    private var pitchSpeed: Float = 0
    /// The fur's lean in world space, and how fast it is changing.
    private var push = simd_float3(repeating: 0)
    private var pushSpeed = simd_float3(repeating: 0)
    /// How squeezed it is: 0 at rest, positive when pressed, negative when stretched.
    private var squeeze: Float = 0
    private var squeezeSpeed: Float = 0
    /// Seconds of head-shake left.
    private var shaking: Float = 0

    func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
        let dt = last == 0 ? 1.0 / 60 : Float(min(max(time - last, 1.0 / 240), 1.0 / 30))
        last = time
        let now = wishes.withLock { wishes -> Wishes in
            let taken = wishes
            wishes.turn = 0
            wishes.tilt = 0
            wishes.stroke = simd_float3(repeating: 0)
            wishes.spin = nil
            wishes.squeeze = 0
            wishes.shake = false
            wishes.launch = false
            wishes.land = false
            return taken
        }
        clock += dt
        let alive: Float = now.still ? 0 : 1

        // Fluff overshoots a little on the way up, so it puffs instead of sliding.
        fluffSpeed += (-70 * (fluff - now.fluff) - 9 * fluffSpeed) * dt
        fluff += fluffSpeed * dt

        // Spin: the finger sets it directly; let go, it coasts and slows.
        yaw += now.turn
        if now.held { spin = 0 }
        if let released = now.spin { spin = released }
        yaw += spin * dt
        spin *= exp(-1.6 * dt)

        // Tip: follows the finger, then swings back upright.
        pitch = min(max(pitch + now.tilt, -0.7), 0.7)
        if !now.held {
            pitchSpeed += (-70 * pitch - 8 * pitchSpeed) * dt
            pitch += pitchSpeed * dt
        } else {
            pitchSpeed = 0
        }

        // Fur: pushed by a stroke, trailing behind a spin, stirred by a little air.
        let breeze = simd_float3(sin(clock * 0.9), 0.5 * sin(clock * 1.3 + 1), 0) * (0.012 * alive)
        let trail = simd_float3(-spin * 0.02, 0, 0)
        pushSpeed += now.stroke
        pushSpeed += (-95 * (push - trail - breeze) - 8 * pushSpeed) * dt
        push += pushSpeed * dt
        let reach = simd_length(push)
        if reach > 0.2 { push *= 0.2 / reach }

        // Squeeze: held down under a finger, a kick from a tap, a stretch on take-off and
        // a squash on landing; it rings a little before it settles.
        // With Reduce Motion on (`still`) it neither spins away nor squashes on landing.
        if now.launch, !now.still {
            squeezeSpeed -= 3.4
            spin += 15
        }
        if now.land, !now.still { squeezeSpeed += 4.5 }
        squeezeSpeed += now.squeeze
        squeezeSpeed += (-260 * (squeeze - (now.held ? 0.09 : 0)) - 13 * squeezeSpeed) * dt
        squeeze += squeezeSpeed * dt

        if now.shake, !now.still { shaking = 0.5 }
        shaking = max(0, shaking - dt)

        let sway = alive * 0.2 * sin(clock * 0.8)
        let shake = shaking > 0 ? 0.42 * sin((0.5 - shaking) * 38) * (shaking / 0.5) : 0
        // Hopping: up on half a sine, flattened a touch on landing. Not while it is held.
        let hopping = now.eager && !now.held
        let hop = hopping ? alive * abs(sin(clock * 3.4)) : 0
        let thud = hopping ? alive * max(0, 1 - hop * 6) * 0.06 : 0
        let pressed = min(max(squeeze, -0.25), 0.3) + thud

        toy.body.simdOrientation = simd_quatf(angle: -0.24, axis: simd_float3(0, 0, 1))
            * simd_quatf(angle: 0.2 + pitch, axis: simd_float3(1, 0, 0))
            * simd_quatf(angle: yaw + sway + shake, axis: simd_float3(0, 1, 0))
        toy.body.simdPosition = simd_float3(0, 0.2 * hop + alive * 0.04 * sin(clock * 1.3) - 0.5 * pressed, 0)
        // Squeezed, it gets shorter and fatter; stretched, the reverse.
        toy.body.simdScale = simd_float3(1 + 0.5 * pressed, 1 - pressed, 1 + 0.5 * pressed)

        toy.fluff = fluff
        toy.push = push
        toy.refresh()
    }
}
#endif
