import SceneKit
import simd

// MARK: - PlushShuttlecock
// A shuttlecock made of plush, lit and furred in real time.
//
// The fur is shell texturing: each furry part is its skin plus a stack of copies pushed
// outward, and on every copy the shader keeps only the spots a strand passes through. A
// strand is a column of those spots that narrows to a point, so the pile is dense and dark
// at the root and fine and bright at the tip.
//
// All the shells of a part are one mesh drawn with one material: every vertex carries the
// depth of the shell it belongs to. That makes a part one draw call, and a frame's worth of
// motion three numbers per part.
//
// Pushed straight out along the normal, fur stands like a hedgehog's spines. Three things
// make it read as plush instead: every strand is combed along the surface toward the rim,
// the tips lean with whatever pushes them (gravity, a stroke, the body's own motion), and
// strands differ in length and brightness so no grid shows.
//
// `fluff` is the one expressive control: 0 is short and combed flat, 1 stands up full.

public final class PlushShuttlecock {
    public let scene = SCNScene()
    public let camera = SCNNode()
    /// Spin, tilt and move this. It turns about the toy's middle, not its cork.
    public let body = SCNNode()
    /// Holds the furry parts, lowered so the model's middle sits on `body`'s origin.
    private let model = SCNNode()

    /// 0 = short and lying down, 1 = fully fluffed up.
    public var fluff: Float = 1
    /// A push on the fur tips in world space, in model units: a stroke, wind, drag inertia.
    public var push = simd_float3(repeating: 0)

    /// How far the tips droop under their own weight, in model units.
    private static let droop: Float = 0.045

    private struct Part {
        let material: SCNMaterial
        /// Pile length at full fluff, in model units.
        let length: Float
        /// How strongly the pile is combed along the surface when it lies flat.
        let comb: Float
    }

    private var parts: [Part] = []

    public init() {
        build()
        refresh()
    }

    /// Sends the current fluff, push and orientation to the fur. Call once a frame, after
    /// moving `body`.
    public func refresh() {
        // The shader works in the body's own space; what pushes the fur is in the world's.
        let world = push + simd_float3(0, -Self.droop, 0)
        let lean = simd_act(body.simdWorldOrientation.inverse, world)
        let leanValue = NSValue(scnVector3: SCNVector3(lean.x, lean.y, lean.z))
        let raised = min(max(fluff, 0), 1)
        for part in parts {
            // Lying flat is shorter and combed harder; fluffed is longer and stands off the skin.
            part.material.setValue(NSNumber(value: part.length * (0.34 + 0.66 * raised)), forKey: "furLength")
            part.material.setValue(NSNumber(value: part.comb * (1.7 - 1.2 * raised)), forKey: "furComb")
            part.material.setValue(leanValue, forKey: "furLean")
        }
    }

    // MARK: Building

    private func build() {
        // Feathers: warm white pile with lilac in the shade, so it sits with the app's
        // aubergine ink on any of the page's colours.
        let skirt = Self.lathe(rings: 56, segments: 144, surface: Self.skirtSurface)
        add(skirt, shells: 32, length: 0.24, comb: 0.7, density: 52,
            root: Self.linear(0xB4A8CC), tip: Self.linear(0xFFFDF8))

        // Cork: a short dark pile, the ink of the page's type.
        let cork = Self.lathe(rings: 24, segments: 72, surface: Self.corkSurface)
        add(cork, shells: 16, length: 0.09, comb: 0.5, density: 60,
            root: Self.linear(0x120E19), tip: Self.linear(0x66597E))

        model.simdPosition = simd_float3(0, -Self.middle, 0)
        body.addChildNode(model)
        scene.rootNode.addChildNode(body)

        let lens = SCNCamera()
        lens.fieldOfView = 26
        lens.zNear = 0.1
        lens.zFar = 60
        camera.camera = lens
        camera.simdPosition = simd_float3(0, 0.25, 9.6)
        camera.simdLook(at: simd_float3(0, 0, 0))
        scene.rootNode.addChildNode(camera)
    }

    /// Adds a furry part: `skin` stacked `shells` deep into one mesh, each copy's vertices
    /// tagged with how far up the pile it sits (0 on the skin, 1 at the tips).
    private func add(_ skin: Skin, shells: Int, length: Float, comb: Float, density: Float,
                     root: simd_float3, tip: simd_float3) {
        let count = skin.positions.count
        var positions: [SCNVector3] = []
        var normals: [SCNVector3] = []
        var depths: [CGPoint] = []
        var indices: [UInt32] = []
        positions.reserveCapacity(count * shells)
        normals.reserveCapacity(count * shells)
        depths.reserveCapacity(count * shells)
        indices.reserveCapacity(skin.indices.count * shells)
        // Skin first, tips last: the order they are drawn in.
        for shell in 0..<shells {
            let depth = CGFloat(shell) / CGFloat(shells - 1)
            let first = UInt32(shell * count)
            positions += skin.positions
            normals += skin.normals
            depths += [CGPoint](repeating: CGPoint(x: depth, y: 0), count: count)
            indices += skin.indices.map { $0 + first }
        }

        let material = SCNMaterial()
        // Lit in the shader, so the look is the same wherever the view is put.
        material.lightingModel = .constant
        material.shaderModifiers = [.geometry: Self.shellGeometry, .surface: Self.shellSurface]
        material.setValue(NSNumber(value: density), forKey: "furDensity")
        material.setValue(NSValue(scnVector3: SCNVector3(root.x, root.y, root.z)), forKey: "furRoot")
        material.setValue(NSValue(scnVector3: SCNVector3(tip.x, tip.y, tip.z)), forKey: "furTip")

        let geometry = SCNGeometry(
            sources: [SCNGeometrySource(vertices: positions), SCNGeometrySource(normals: normals),
                      SCNGeometrySource(textureCoordinates: depths)],
            elements: [SCNGeometryElement(indices: indices, primitiveType: .triangles)])
        geometry.materials = [material]
        model.addChildNode(SCNNode(geometry: geometry))
        parts.append(Part(material: material, length: length, comb: comb))
    }

    // MARK: Shape

    /// Height of the model's middle above its pole: what `body` turns about.
    private static let middle: Float = 1.5

    /// The feather skirt as a stuffed toy would have it: a trumpet rising from the cork,
    /// rippled into sixteen feathers, that rolls over a plump rim and closes in a shallow
    /// dish on top. A real skirt is open; closed, it has no bare inside to show when spun.
    /// `s` runs from the cork (0) up the outside, over the rim, to the centre of the top (1).
    private static func skirtSurface(_ s: Float, _ angle: Float) -> simd_float3 {
        let rimRadius: Float = 1.2, rimHeight: Float = 2.7, roll: Float = 0.2
        var radius: Float, height: Float
        if s < 0.68 {
            // Up the outside.
            let u = s / 0.68
            radius = 0.37 + (rimRadius - 0.37) * pow(u, 1.28)
            height = 0.64 + (rimHeight - 0.64) * u
        } else if s < 0.84 {
            // Over the rim: half a turn of a roll.
            let turn = (s - 0.68) / 0.16 * .pi
            radius = rimRadius - roll + roll * cos(turn)
            height = rimHeight + roll * 0.9 * sin(turn)
        } else {
            // Across the top to the axis, dipping in the middle.
            let u = (s - 0.84) / 0.16
            radius = (rimRadius - 2 * roll) * (1 - u)
            height = rimHeight - 0.26 * (1 - (1 - u) * (1 - u))
        }
        // Feathers bulge between their seams, more toward the rim and not at all on the axis.
        let spread = min(radius / rimRadius, 1)
        radius *= 1 + 0.055 * spread * cos(16 * angle)
        return simd_float3(radius * cos(angle), height, radius * sin(angle))
    }

    /// The cork: most of a ball, sitting on its pole. `s` runs from the pole (0) upward.
    private static func corkSurface(_ s: Float, _ angle: Float) -> simd_float3 {
        let ball: Float = 0.52
        let t = s * 0.66 * .pi
        let radius = ball * sin(t)
        return simd_float3(radius * cos(angle), ball * (1 - cos(t)), radius * sin(angle))
    }

    /// One layer of a part: the mesh of its skin.
    private struct Skin {
        var positions: [SCNVector3] = []
        var normals: [SCNVector3] = []
        var indices: [UInt32] = []
    }

    /// A surface of revolution about the y axis with smooth normals. `surface` must run from
    /// the bottom of the shape up its outside as `s` grows, so the normals come out pointing
    /// outward all the way round.
    private static func lathe(rings: Int, segments: Int,
                              surface: (_ s: Float, _ angle: Float) -> simd_float3) -> Skin {
        var positions: [SCNVector3] = []
        var normals: [SCNVector3] = []
        let step: Float = 0.001
        for ring in 0...rings {
            let s = Float(ring) / Float(rings)
            for segment in 0...segments {
                let angle = Float(segment) / Float(segments) * 2 * .pi
                let p = surface(s, angle)
                let alongRing = surface(s, angle + step) - surface(s, angle - step)
                let upRing = surface(min(s + step, 1), angle) - surface(max(s - step, 0), angle)
                var normal = simd_cross(upRing, alongRing)
                let size = simd_length(normal)
                if size > 1e-9 {
                    normal /= size
                } else {
                    // On the axis the ring has no width: the surface faces straight down at
                    // the bottom pole and straight up at the top one.
                    normal = simd_float3(0, s < 0.5 ? -1 : 1, 0)
                }
                positions.append(SCNVector3(p.x, p.y, p.z))
                normals.append(SCNVector3(normal.x, normal.y, normal.z))
            }
        }
        var indices: [UInt32] = []
        let row = UInt32(segments + 1)
        for ring in 0..<UInt32(rings) {
            for segment in 0..<UInt32(segments) {
                let a = ring * row + segment
                let b = a + 1
                let c = a + row
                let d = c + 1
                indices += [a, c, b, b, c, d]
            }
        }
        return Skin(positions: positions, normals: normals, indices: indices)
    }

    /// sRGB hex to the linear values the shader works in.
    private static func linear(_ hex: UInt32) -> simd_float3 {
        func channel(_ shift: UInt32) -> Float {
            let c = Float((hex >> shift) & 0xFF) / 255
            return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return simd_float3(channel(16), channel(8), channel(0))
    }

    // MARK: Shaders

    /// Moves a shell off the skin, by the depth its vertices carry: out along the normal, then
    /// combed along the surface toward the rim and leaned by `furLean`. Both grow with the square of the depth, so strands
    /// curve from a fixed root instead of sliding sideways.
    private static let shellGeometry = """
    #pragma arguments
    float furLength;
    float furComb;
    float3 furLean;
    #pragma varyings
    float3 furBase;
    float furShellDepth;
    #pragma body
    float furShell = _geometry.texcoords[0].x;
    out.furShellDepth = furShell;
    float3 furNormal = normalize(_geometry.normal);
    float3 furUp = float3(0.0, 1.0, 0.0);
    float3 furAlong = furUp - furNormal * dot(furUp, furNormal);
    float furAlongLength = length(furAlong);
    furAlong = furAlongLength > 0.0001 ? furAlong / furAlongLength : float3(0.0, 0.0, 0.0);
    float furBend = furShell * furShell;
    out.furBase = _geometry.position.xyz;
    _geometry.position.xyz += furNormal * (furShell * furLength)
        + furAlong * (furComb * furBend * furLength)
        + furLean * furBend;
    """

    /// Keeps the spots where a strand passes and lights them. Strands are placed by hashing
    /// a 3-D grid over the skin (no texture, so no seam), each with its own centre, length
    /// and brightness, and they splay a little by patch so the pile gathers into tufts. The
    /// skin itself (depth 0) is drawn whole, so nothing shows through.
    private static let shellSurface = """
    #pragma arguments
    float furDensity;
    float3 furRoot;
    float3 furTip;
    #pragma body
    float furDepth = in.furShellDepth;
    float3 furTuft = float3(sin(in.furBase.y * 9.0 + in.furBase.z * 7.0),
                            sin(in.furBase.z * 8.0 + in.furBase.x * 6.0),
                            sin(in.furBase.x * 9.5 + in.furBase.y * 5.0));
    float3 furGrid = (in.furBase + furTuft * (furDepth * furDepth * 0.022)) * furDensity;
    float3 furCell = floor(furGrid);
    float3 furOffset = furGrid - furCell - 0.5;
    float furA = fract(sin(dot(furCell, float3(127.1, 311.7, 74.7))) * 43758.5453);
    float furB = fract(sin(dot(furCell, float3(269.5, 183.3, 246.1))) * 43758.5453);
    float furC = fract(sin(dot(furCell, float3(113.5, 271.9, 124.6))) * 43758.5453);
    float3 furCentre = (float3(furA, furB, furC) - 0.5) * 0.7;
    float furReach = 0.55 + 0.45 * furB;
    float furWidth = 0.62 * (1.0 - furDepth / furReach);
    if (furDepth > 0.0 && length(furOffset - furCentre) > furWidth) {
        discard_fragment();
    }

    float3 furN = normalize(_surface.normal);
    float3 furV = normalize(_surface.view);
    float3 furL = normalize(float3(-0.42, 0.78, 0.46));
    float furWrap = clamp((dot(furN, furL) + 0.55) / 1.55, 0.0, 1.0);
    float furShade = mix(0.6, 1.0, pow(furDepth, 0.6));
    float furRim = pow(1.0 - clamp(dot(furN, furV), 0.0, 1.0), 2.4) * (0.25 + 0.75 * furDepth);
    float3 furPile = mix(furRoot, furTip, pow(furDepth, 0.5)) * (0.93 + 0.14 * furA) * (0.96 + 0.04 * furTuft.x);
    float3 furLit = furPile * (0.7 + 0.42 * furWrap) * furShade + furTip * furRim * 0.3;
    _surface.diffuse = float4(furLit, 1.0);
    """
}
