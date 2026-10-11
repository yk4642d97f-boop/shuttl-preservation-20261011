import CryptoKit
import Darwin
import Foundation
import ShuttlAnalysis
import ShuttlCore

/// What MatchPipeline.analyzeLocally (iOS/Sources/Services/MatchPipeline.swift:395-402) does
/// with a returned analysis: "done" or `analysisUnusable(<Chinese sentence>)`.
func appVerdict(_ a: MatchAnalysis) -> (done: Bool, message: String) {
    switch a.outcome {
    case .complete: return (true, a.outcome.userMessage)
    case .stageFailed(_, _, true) where a.hasUsableResult(): return (true, a.outcome.userMessage)
    case let other: return (false, other.userMessage)
    }
}

/// failureReason(for:) for an error thrown out of analyze (MatchPipeline.swift:384 + :693-695).
func appThrownMessage(_ error: Error) -> String {
    let info = String(describing: error)
    return "AI 分析失败：\(info.count > 120 ? String(info.prefix(120)) + "…" : info)"
}

func sha(_ d: Data) -> String { SHA256.hash(data: d).prefix(8).map { String(format: "%02x", $0) }.joined() }

/// Result identity without timing/diagnostics: whole analysis + per-part hashes.
func signatures(_ a: MatchAnalysis) throws -> [String: String] {
    let e = ShuttlJSON.encoder()
    var core = a
    core.diagnostics = [:]; core.processingTimeSeconds = 0
    return ["all": sha(try e.encode(core)), "track": sha(try e.encode(a.track)), "camera": sha(try e.encode(a.camera)),
            "players": sha(try e.encode(a.players)), "hits": sha(try e.encode(a.hits)),
            "segments": sha(try e.encode(a.segments)), "rallies": sha(try e.encode(a.rallies)), "score": sha(try e.encode(a.score))]
}

/// IMPLAUSIBLE checks: speeds, landings outside the hall, time going backwards, events off the clip.
func plausibility(_ a: MatchAnalysis) -> [String] {
    var bad: [String] = []
    let shots = a.rallies.flatMap(\.shots)
    let speeds = shots.compactMap { $0.segment?.speed0Kmh } + a.segments.map(\.speed0Kmh)
    if speeds.contains(where: { !$0.isFinite }) { bad.append("non-finite speed") }
    if let m = speeds.filter(\.isFinite).max(), m > 450 { bad.append(String(format: "speed %.0f km/h > 450", m)) }
    let hallX = CourtModel.halfLength + 4, hallY = CourtModel.doublesHalfWidth + 3
    let landings = a.segments.compactMap(\.landingXY) + a.rallies.compactMap(\.landingXY)
    for l in landings where !(abs(l.x) <= hallX && abs(l.y) <= hallY) {
        bad.append(String(format: "landing (%.1f, %.1f) m outside hall", l.x, l.y)); break
    }
    let ts = a.meta.timestamps
    if zip(ts, ts.dropFirst()).contains(where: { !($1 > $0) }) { bad.append("meta timestamps not increasing") }
    if a.hits.contains(where: { $0.frame < 0 || $0.frame >= a.meta.nFrames }) { bad.append("hit frame outside clip") }
    for r in a.rallies where r.startFrame > r.endFrame || r.endFrame >= a.meta.nFrames { bad.append("rally frame range invalid"); break }
    if let t = a.track, t.n != a.meta.nFrames { bad.append("track length \(t.n) != frames \(a.meta.nFrames)") }
    return bad
}

func summary(_ a: MatchAnalysis, clip: String, seconds: Double) throws -> [String: Any] {
    let speeds = a.rallies.flatMap(\.shots).compactMap { $0.segment?.speed0Kmh }.filter(\.isFinite)
    let verdict = appVerdict(a)
    let stageData = try ShuttlJSON.encoder().encode(a.diagnostics["stages"] ?? .null)
    let calData = try ShuttlJSON.encoder().encode(a.diagnostics["calibration_auto"] ?? .null)
    let ts = a.meta.timestamps
    return ["clip": clip, "status": "returned", "frames": a.meta.nFrames, "fps": a.meta.fps,
            "size": [a.meta.width, a.meta.height], "rotation": a.meta.rotationDeg,
            "duration_s": Double(ts.last ?? 0), "camera": a.camera != nil, "visible": a.visibleShuttleFrames,
            "hits": a.hits.count, "rallies": a.rallies.count, "shots": a.rallies.flatMap(\.shots).count,
            "hit_frames": a.hits.map(\.frame), "max_speed_kmh": speeds.max() ?? 0,
            "outcome": a.outcome.userMessage, "app_done": verdict.done, "app_message": verdict.message,
            "stage_failures": a.stageFailures.map { "\($0.stage): \($0.message)" },
            "implausible": plausibility(a), "signature": try signatures(a),
            "stages": try JSONSerialization.jsonObject(with: stageData, options: [.fragmentsAllowed]),
            "calibration_auto": try JSONSerialization.jsonObject(with: calData, options: [.fragmentsAllowed]),
            "seconds": seconds, "peak_footprint_mb": peakFootprintMB()]
}

/// Lifetime peak physical footprint of this process (what jetsam judges on iOS).
func peakFootprintMB() -> Double {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count) }
    }
    return kr == KERN_SUCCESS ? (Double(info.ledger_phys_footprint_peak) / 1_048_576 * 10).rounded() / 10 : -1
}

/// Makes any value JSONSerialization-safe (non-finite → null, unknown → its description).
func jsonSafe(_ v: Any) -> Any {
    switch v {
    case let d as [String: Any]: return d.mapValues(jsonSafe)
    case let a as [Any]: return a.map(jsonSafe)
    case let x as Double: return x.isFinite ? x : NSNull()
    case let x as Int: return x
    case let x as Bool: return x
    case let x as String: return x
    case is NSNull: return v
    case let x as NSNumber: return x
    default:
        let m = Mirror(reflecting: v)
        if m.displayStyle == .optional { return m.children.first.map { jsonSafe($0.value) } ?? NSNull() }
        return String(describing: v)
    }
}

func emit(_ obj: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: jsonSafe(obj), options: [.sortedKeys, .fragmentsAllowed]) {
        print(String(decoding: d, as: UTF8.self)); fflush(stdout)
    }
}
