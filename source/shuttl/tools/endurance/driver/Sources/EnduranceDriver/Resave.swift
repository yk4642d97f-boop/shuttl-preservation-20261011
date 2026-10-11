import Foundation
import ShuttlAnalysis
import ShuttlCore
import ShuttlRuntime

/// `resave <run-dir> <match-uuid>`: the library's load + save of a finished analysis,
/// measured on its own (the analyze command stops its 1 s sampler before archive.save).
/// Loads the archived MatchAnalysis the way the app does, then saves it again into
/// <run-dir>/resave/ exactly as AnalysisArchive.save does after an analysis.
func resave(runDir: URL, id: UUID) throws {
    let archive = AnalysisArchive(analysesDirectory: runDir.appendingPathComponent("archive"),
                                  checkpointsDirectory: runDir.appendingPathComponent("checkpoints"))
    let base = ResourceSnapshot.now()
    let t0 = ProcessInfo.processInfo.systemUptime
    let loaded = try archive.load(matchID: id)
    let afterLoad = ResourceSnapshot.now()
    let t1 = ProcessInfo.processInfo.systemUptime
    let out = AnalysisArchive(analysesDirectory: runDir.appendingPathComponent("resave"),
                              checkpointsDirectory: runDir.appendingPathComponent("resave-ck"))
    let url = try out.save(loaded, matchID: id)
    let afterSave = ResourceSnapshot.now()
    let t2 = ProcessInfo.processInfo.systemUptime
    // The same players with keypoints, as the checkpoint store writes them.
    let ck = runDir.appendingPathComponent("resave/players-with-keypoints.bin")
    try PlayersCodec.write(loaded.players, to: ck, fingerprint: "resave", includeKeypoints: true)
    let t3 = ProcessInfo.processInfo.systemUptime
    let back = try PlayersCodec.read(from: ck, expectedFingerprint: "resave")
    let t4 = ProcessInfo.processInfo.systemUptime
    let end = ResourceSnapshot.now()
    let r: [String: Any] = [
        "players": loaded.players.count, "players_roundtrip_equal_count": back?.count == loaded.players.count,
        "footprint_before_mb": base.physFootprintMB, "footprint_after_load_mb": afterLoad.physFootprintMB,
        "peak_after_load_mb": afterLoad.peakPhysFootprintMB, "peak_after_save_mb": afterSave.peakPhysFootprintMB,
        "peak_end_mb": end.peakPhysFootprintMB, "load_s": t1 - t0, "save_s": t2 - t1,
        "players_keypoints_write_s": t3 - t2, "players_keypoints_read_s": t4 - t3,
        "json_bytes": EnduranceSupport.fileSize(url),
        "players_bin_slim_bytes": EnduranceSupport.fileSize(out.playersURL(matchID: id)),
        "players_bin_keypoints_bytes": EnduranceSupport.fileSize(ck),
    ]
    let data = try JSONSerialization.data(withJSONObject: r, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: runDir.appendingPathComponent("resave.json"), options: .atomic)
    print(String(data: data, encoding: .utf8) ?? "{}")
    try? FileManager.default.removeItem(at: runDir.appendingPathComponent("resave"))
}
