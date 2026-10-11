import AVFoundation
import CoreVideo
import Foundation
import VideoToolbox

/// Streams decoded source frames into a writer input, one at a time (never buffers the clip).
final class VideoFeed: @unchecked Sendable {
    let input: AVAssetWriterInput
    let adaptor: AVAssetWriterInputPixelBufferAdaptor
    let reader: AVAssetReader
    let output: AVAssetReaderTrackOutput
    let mode: String
    let fps: Double
    let durationSeconds: Double
    var index = 0          // capture index of the next decoded source frame
    var written = 0
    var rng = SplitMix(seed: 81010)
    var transfer: VTPixelTransferSession?

    init(src: URL, mode: String, writer: AVAssetWriter) {
        let asset = AVURLAsset(url: src)
        guard let track = asset.tracks(withMediaType: .video).first else { fail("no video in source") }
        fps = Double(track.nominalFrameRate > 0 ? track.nominalFrameRate : 30)
        durationSeconds = CMTimeGetSeconds(asset.duration) + (mode == "jump" ? 5 : 0)
        let size = track.naturalSize
        let w = Int(size.width), h = Int(size.height)
        guard let r = try? AVAssetReader(asset: asset) else { fail("reader") }
        reader = r
        output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        reader.add(output)
        self.mode = mode
        var settings: [String: Any] = [AVVideoWidthKey: w, AVVideoHeightKey: h, AVVideoCodecKey: AVVideoCodecType.h264]
        var compression: [String: Any] = [AVVideoAllowFrameReorderingKey: false, AVVideoMaxKeyFrameIntervalKey: 30]
        var pixelFormat = kCVPixelFormatType_32BGRA
        switch mode {
        case "longgop":
            compression = [AVVideoAllowFrameReorderingKey: true, AVVideoMaxKeyFrameIntervalKey: 600,
                           AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel]
        case "hdr10":
            settings[AVVideoCodecKey] = AVVideoCodecType.hevc
            compression = [AVVideoProfileLevelKey: kVTProfileLevel_HEVC_Main10_AutoLevel as String,
                           AVVideoAllowFrameReorderingKey: true]
            settings[AVVideoColorPropertiesKey] = [AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_2020,
                AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_2100_HLG,
                AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_2020]
            pixelFormat = kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange
        default: break
        }
        settings[AVVideoCompressionPropertiesKey] = compression
        input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = false
        if mode.hasPrefix("rot"), let deg = Double(mode.dropFirst(3)) { input.transform = CGAffineTransform(rotationAngle: deg * .pi / 180) }
        adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: pixelFormat, kCVPixelBufferWidthKey as String: w,
            kCVPixelBufferHeightKey as String: h, kCVPixelBufferIOSurfacePropertiesKey as String: [:] as [String: Any]])
        guard writer.canAdd(input) else { fail("cannot add video input for mode \(mode)") }
        writer.add(input)
        if mode == "hdr10" { VTPixelTransferSessionCreate(allocator: nil, pixelTransferSessionOut: &transfer) }
        guard reader.startReading() else { fail("reader start: \(reader.error.map { "\($0)" } ?? "?")") }
    }

    /// Presentation time for capture index i, or nil to drop the frame.
    func pts(_ i: Int) -> CMTime? {
        let scale: Int32 = 600
        let base = CMTime(value: Int64((Double(i) / fps * Double(scale)).rounded()), timescale: scale)
        switch mode {
        case "vfr": return rng.next() < 0.3 && i > 0 ? nil : base
        case "drop": return (60..<72).contains(i) ? nil : base
        case "jump": return i >= 66 ? CMTimeAdd(base, CMTime(value: 5 * Int64(scale), timescale: scale)) : base
        default: return base
        }
    }

    /// Decodes and appends the next kept frame. false at end of stream.
    func appendNext() -> Bool {
        while let sb = output.copyNextSampleBuffer() {
            defer { index += 1 }
            guard let pb = CMSampleBufferGetImageBuffer(sb), let t = pts(index) else { continue }
            let frame = transfer == nil ? pb : convert10(pb)
            guard adaptor.append(frame, withPresentationTime: t) else {
                fail("append frame \(index) mode \(mode): \(adaptor.assetWriterInput.description)")
            }
            written += 1
            return true
        }
        return false
    }

    /// BGRA (sRGB-ish) → 4:2:0 10-bit video range tagged BT.2020 / HLG, like an iPhone HDR capture.
    private func convert10(_ pb: CVPixelBuffer) -> CVPixelBuffer {
        var outPB: CVPixelBuffer?
        guard let pool = adaptor.pixelBufferPool,
              CVPixelBufferPoolCreatePixelBuffer(nil, pool, &outPB) == kCVReturnSuccess, let dst = outPB else { fail("10-bit pool") }
        CVBufferSetAttachment(dst, kCVImageBufferColorPrimariesKey, kCVImageBufferColorPrimaries_ITU_R_2020, .shouldPropagate)
        CVBufferSetAttachment(dst, kCVImageBufferTransferFunctionKey, kCVImageBufferTransferFunction_ITU_R_2100_HLG, .shouldPropagate)
        CVBufferSetAttachment(dst, kCVImageBufferYCbCrMatrixKey, kCVImageBufferYCbCrMatrix_ITU_R_2020, .shouldPropagate)
        let st = VTPixelTransferSessionTransferImage(transfer!, from: pb, to: dst)
        if st != noErr { fail("VTPixelTransfer \(st)") }
        return dst
    }
}

/// Deterministic PRNG (fixed seed → reproducible VFR drop pattern).
struct SplitMix {
    var state: UInt64
    init(seed: UInt64) { state = seed }
    mutating func next() -> Double {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return Double((z ^ (z >> 31)) >> 11) / Double(1 << 53)
    }
}
