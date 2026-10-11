import AVFoundation
import Foundation

func makeClip(seconds: Double, output: URL, sources: [URL], codec: String = "h264") async throws {
    guard seconds > 0, !sources.isEmpty else { throw NSError(domain: "Endurance", code: 1) }
    let composition = AVMutableComposition()
    guard let videoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
        throw NSError(domain: "Endurance", code: 2)
    }
    let target = CMTime(seconds: seconds, preferredTimescale: 600)
    let frame = CMTime(value: 1, timescale: 30)
    // Deterministic LCG: each pass over the rallies uses a new order, and every gap
    // (dead time between rallies: pick-up, serve prep) lasts 8-20 s.
    var rng: UInt64 = 0x5eed_1111
    func next() -> UInt64 { rng = rng &* 6364136223846793005 &+ 1442695040888963407; return rng >> 33 }
    var order: [URL] = []
    var cursor = CMTime.zero
    var index = 0
    var naturalSize = CGSize.zero
    while cursor < target {
        if order.isEmpty {
            order = sources
            for i in stride(from: order.count - 1, to: 0, by: -1) { order.swapAt(i, Int(next() % UInt64(i + 1))) }
        }
        let hold = CMTime(seconds: 8 + Double(next() % 1201) / 100, preferredTimescale: 600)
        let asset = AVURLAsset(url: order.removeFirst())
        index += 1
        guard let track = try await asset.loadTracks(withMediaType: .video).first else { continue }
        let (range, size) = try await track.load(.timeRange, .naturalSize)
        naturalSize = size
        let remaining = CMTimeSubtract(target, cursor)
        let needsHold = CMTimeCompare(remaining, CMTimeAdd(range.duration, frame)) > 0
        let clipDuration = CMTimeMinimum(needsHold ? CMTimeSubtract(range.duration, frame) : range.duration, remaining)
        try videoTrack.insertTimeRange(CMTimeRange(start: range.start, duration: clipDuration), of: track, at: cursor)
        cursor = CMTimeAdd(cursor, clipDuration)
        if needsHold && CMTimeCompare(CMTimeSubtract(target, cursor), CMTimeAdd(frame, hold)) >= 0 {
            let freeze = CMTimeRange(start: CMTimeAdd(range.start, CMTimeSubtract(range.duration, frame)), duration: frame)
            try videoTrack.insertTimeRange(freeze, of: track, at: cursor)
            let freezeOutput = CMTimeRange(start: cursor, duration: frame)
            let holdDuration = CMTimeMinimum(hold, CMTimeSubtract(target, cursor))
            videoTrack.scaleTimeRange(freezeOutput, toDuration: holdDuration)
            cursor = CMTimeAdd(cursor, holdDuration)
        }
    }
    let video = AVMutableVideoComposition()
    video.renderSize = CGSize(width: 1920, height: 1080)
    video.frameDuration = CMTime(value: 1, timescale: 60)
    let instruction = AVMutableVideoCompositionInstruction()
    instruction.timeRange = CMTimeRange(start: .zero, duration: target)
    let layer = AVMutableVideoCompositionLayerInstruction(assetTrack: videoTrack)
    layer.setTransform(CGAffineTransform(scaleX: 1920 / naturalSize.width, y: 1080 / naturalSize.height), at: .zero)
    instruction.layerInstructions = [layer]
    video.instructions = [instruction]

    try? FileManager.default.removeItem(at: output)
    let preset = codec == "hevc" ? AVAssetExportPresetHEVCHighestQuality : AVAssetExportPreset1920x1080
    guard let exporter = AVAssetExportSession(asset: composition, presetName: preset) else {
        throw NSError(domain: "Endurance", code: 3)
    }
    exporter.videoComposition = video
    exporter.outputURL = output
    exporter.outputFileType = codec == "hevc" ? .mov : .mp4
    await exporter.export()
    guard exporter.status == .completed else { throw exporter.error ?? NSError(domain: "Endurance", code: 4) }
    print("created \(output.path) (~\(Int(seconds))s), codec=\(codec), source segments=\(index)")
}
