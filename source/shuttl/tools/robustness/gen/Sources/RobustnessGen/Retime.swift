import AVFoundation
import CoreVideo
import Foundation
import VideoToolbox

/// `RobustnessGen retime <src> <out> <mode>` — re-encodes REAL footage with controlled timing,
/// codec and container properties. Timestamps stay truthful (capture index / fps) unless the
/// mode is a deliberate lie (`jump`). Modes:
///   reencode  plain H.264, every frame                      vfr   ~30 % of frames dropped at random (seeded), true PTS
///   drop      frames 60..<72 missing (encoder hiccup)       jump  +5 s PTS jump from frame 66 on (clock lie)
///   longgop   H.264 High, B-frames, keyframe every 600      hdr10 HEVC Main10 4:2:0 10-bit, BT.2020 / HLG tags
///   audio     H.264 + AAC track (audio is track 1)          audioonly  AAC only, no video track
///   rotN      H.264 with an N° preferred transform (rot90 portrait, rot180 = landscape-right iPhone)
func retimeMain(_ args: [String]) {
    guard args.count >= 3 else { fail("usage: RobustnessGen retime <src> <out> <mode>") }
    let src = URL(fileURLWithPath: args[0]), out = URL(fileURLWithPath: args[1]), mode = args[2]
    try? FileManager.default.removeItem(at: out)
    let type: AVFileType = out.pathExtension.lowercased() == "mp4" ? .mp4 : .mov
    guard let writer = try? AVAssetWriter(outputURL: out, fileType: type) else { fail("writer") }
    let group = DispatchGroup()
    var audioIn: AVAssetWriterInput?
    if mode == "audio" || mode == "audioonly" {
        let a = AVAssetWriterInput(mediaType: .audio, outputSettings: [AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: 48000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 64000])
        a.expectsMediaDataInRealTime = false
        guard writer.canAdd(a) else { fail("cannot add audio") }
        writer.add(a); audioIn = a
    }
    var video: VideoFeed?
    if mode != "audioonly" { video = VideoFeed(src: src, mode: mode, writer: writer) }
    guard writer.startWriting() else { fail(writer.error?.localizedDescription ?? "startWriting") }
    writer.startSession(atSourceTime: .zero)
    let duration = video?.durationSeconds ?? 2.0
    if let a = audioIn {
        group.enter()
        let q = DispatchQueue(label: "audio"); var next = 0; let total = Int(duration * 48000)
        a.requestMediaDataWhenReady(on: q) {
            while a.isReadyForMoreMediaData {
                if next >= total { a.markAsFinished(); group.leave(); return }
                let n = min(1024, total - next)
                guard a.append(audioBuffer(start: next, n: n)) else { fail("audio append: \(writer.error.map { "\($0)" } ?? "?")") }
                next += n
            }
        }
    }
    if let v = video {
        group.enter()
        v.input.requestMediaDataWhenReady(on: DispatchQueue(label: "video")) {
            while v.input.isReadyForMoreMediaData {
                if !v.appendNext() { v.input.markAsFinished(); group.leave(); return }
            }
        }
    }
    group.wait()
    let done = DispatchSemaphore(value: 0); writer.finishWriting { done.signal() }; done.wait()
    if writer.status != .completed { fail(writer.error?.localizedDescription ?? "writer failed") }
    print("\(out.path) mode=\(mode) frames_written=\(video?.written ?? 0)")
}

private let audioFormat: CMAudioFormatDescription = {
    var asbd = AudioStreamBasicDescription(mSampleRate: 48000, mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked,
        mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2, mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0)
    var fmt: CMAudioFormatDescription?
    CMAudioFormatDescriptionCreate(allocator: nil, asbd: &asbd, layoutSize: 0, layout: nil, magicCookieSize: 0,
                                   magicCookie: nil, extensions: nil, formatDescriptionOut: &fmt)
    return fmt!
}()

/// 440 Hz sine, 16-bit mono LPCM at 48 kHz, samples start..<start+n.
func audioBuffer(start: Int, n: Int) -> CMSampleBuffer {
    var block: CMBlockBuffer?
    CMBlockBufferCreateWithMemoryBlock(allocator: nil, memoryBlock: nil, blockLength: n * 2, blockAllocator: nil,
        customBlockSource: nil, offsetToData: 0, dataLength: n * 2, flags: kCMBlockBufferAssureMemoryNowFlag, blockBufferOut: &block)
    var pcm = (0..<n).map { Int16(8000 * sin(2 * Double.pi * 440 * Double(start + $0) / 48000)) }
    CMBlockBufferReplaceDataBytes(with: &pcm, blockBuffer: block!, offsetIntoDestination: 0, dataLength: n * 2)
    var sb: CMSampleBuffer?
    CMAudioSampleBufferCreateReadyWithPacketDescriptions(allocator: nil, dataBuffer: block!, formatDescription: audioFormat,
        sampleCount: n, presentationTimeStamp: CMTime(value: Int64(start), timescale: 48000), packetDescriptions: nil, sampleBufferOut: &sb)
    return sb!
}
