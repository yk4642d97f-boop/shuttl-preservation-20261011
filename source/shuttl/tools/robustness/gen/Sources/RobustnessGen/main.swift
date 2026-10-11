import AVFoundation
import CoreVideo
import Foundation

func fail(_ s: String) -> Never { fputs("ERROR: \(s)\n", stderr); exit(2) }
func paint(_ pb: CVPixelBuffer, _ frame: Int) {
    CVPixelBufferLockBaseAddress(pb, [])
    defer { CVPixelBufferUnlockBaseAddress(pb, []) }
    let w=CVPixelBufferGetWidth(pb), h=CVPixelBufferGetHeight(pb), stride=CVPixelBufferGetBytesPerRow(pb)
    guard let base=CVPixelBufferGetBaseAddress(pb) else { return }
    let p=base.assumingMemoryBound(to: UInt8.self)
    for y in 0..<h { for x in 0..<w {
        let i=y*stride+x*4; let line=(x%max(w/6,1)<2 || y%max(h/5,1)<2)
        p[i]=line ? 230 : 25; p[i+1]=line ? 230 : 90; p[i+2]=line ? 230 : 35; p[i+3]=255
    }}
}
let a=CommandLine.arguments
if a.count > 1 && a[1] == "retime" { retimeMain(Array(a.dropFirst(2))); exit(0) }
if a.count < 5 { fail("usage: RobustnessGen <output> <h264|hevc> <rotation-deg> <frames> [fps]") }
let out=URL(fileURLWithPath:a[1]), codec=a[2], rotation=Double(a[3]) ?? 0, n=Int(a[4]) ?? 60
let fps=Double(a.count>5 ? a[5] : "30") ?? 30
try? FileManager.default.removeItem(at:out)
let writer=try AVAssetWriter(outputURL:out,fileType:.mov)
let c: AVVideoCodecType = codec == "hevc" ? .hevc : .h264
let input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:c,AVVideoWidthKey:640,AVVideoHeightKey:360])
input.transform=CGAffineTransform(rotationAngle:rotation * .pi / 180); input.expectsMediaDataInRealTime=false
let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,kCVPixelBufferWidthKey as String:640,kCVPixelBufferHeightKey as String:360,kCVPixelBufferIOSurfacePropertiesKey as String:[:] as [String:Any]])
guard writer.canAdd(input) else { fail("cannot add video input") }; writer.add(input)
writer.startWriting(); writer.startSession(atSourceTime:.zero)
for i in 0..<n {
    while !input.isReadyForMoreMediaData { Thread.sleep(forTimeInterval:0.002) }
    var pb:CVPixelBuffer?; guard CVPixelBufferPoolCreatePixelBuffer(nil,adaptor.pixelBufferPool!,&pb)==kCVReturnSuccess,let pb else { fail("pixel buffer allocation") }
    paint(pb,i); let pts=CMTime(value:Int64(i),timescale:Int32(fps))
    guard adaptor.append(pb,withPresentationTime:pts) else { fail(writer.error?.localizedDescription ?? "append") }
}
input.markAsFinished(); let done=DispatchSemaphore(value:0); writer.finishWriting{done.signal()}; done.wait()
if writer.status != .completed { fail(writer.error?.localizedDescription ?? "writer failed") }
print(out.path)
