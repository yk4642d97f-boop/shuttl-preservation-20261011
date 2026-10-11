import Darwin
import Foundation
import ShuttlLive
import ShuttlAnalysis
import ShuttlCore

final class Stages: AnalysisStages, @unchecked Sendable {
    let stopAt: String?; let lock = NSLock(); var stopped = false
    init(_ stopAt: String? = nil) { self.stopAt = stopAt }
    var detectorName: String { "robustness-fake" }
    func gate(_ s: String) throws {
        if stopAt == s { throw CancellationError() }
        usleep(30_000)
    }
    func detect(_ source: VideoSource, progress: @escaping StageProgress) async throws -> [[ShuttleCandidate]] {
        try gate("detect"); return (0..<source.meta.nFrames).map { [ShuttleCandidate(x: Double($0), y: 2, score: 0.9)] }
    }
    func link(_ c: [[ShuttleCandidate]], meta: VideoMeta) throws -> Track2D {
        try gate("link"); return Track2D(t: meta.timestamps, xy: c.map { [$0[0].x, 2] }, conf: Array(repeating: 0.9, count: c.count), visible: Array(repeating: true, count: c.count), interpolated: Array(repeating: false, count: c.count))
    }
    func calibrationFrames(_ s: VideoSource, count: Int) throws -> [ImageU8] { try gate("calibrate"); return [] }
    func calibrateAutomatic(frames: [ImageU8], size: ImageSize, doublesHint: Bool?) throws -> CameraModel? {
        CameraModel.lookAt(eye: [0,-10,8], target: [0,0,0], focalPx: 120, imageSize: size)
    }
    func calibrateFromPoints(_ p: [String: SIMD2<Double>], size: ImageSize) throws -> CameraModel { throw NSError(domain:"fake",code:1) }
    func refineCamera(_ c: CameraModel, frames: [ImageU8]) throws -> CameraModel { c }
    func trackPlayers(_ s: VideoSource, camera: CameraModel?, step: Int, doubles: Bool?, progress: @escaping StageProgress) async throws -> [PlayerObservation] { try gate("players"); return [] }
    func detectHits(track: Track2D, meta: VideoMeta, camera: CameraModel?, players: [PlayerObservation]?) throws -> [HitEvent] {
        try gate("hits"); return [HitEvent(frame: 1, t: 0.03, xyPx: [1,2]), HitEvent(frame: 3, t: 0.1, xyPx: [3,2])]
    }
    func reconstruct(track: Track2D, hits: [HitEvent], camera: CameraModel, meta: VideoMeta, players: [PlayerObservation]?) throws -> ReconstructionResult { try gate("reconstruct3d"); return .empty }
    func segmentRallies(track: Track2D, hits: [HitEvent], reconstruction: ReconstructionResult, meta: VideoMeta, camera: CameraModel?, players: [PlayerObservation]?) throws -> [RallyV2] { try gate("rallies"); return hits.count > 1 ? [RallyV2(startFrame: 0,endFrame: 3)] : [] }
    func classifyShots(_ r: RallyV2, camera: CameraModel?, players: [PlayerObservation]?) throws -> RallyV2 { try gate("shots"); return r }
    func scoreMatch(_ r: [RallyV2]) throws -> [JSONValue] { try gate("score"); return [] }
}
