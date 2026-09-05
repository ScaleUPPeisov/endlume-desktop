import Foundation
import AVFoundation

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let asset = AVURLAsset(url: url)
let sem = DispatchSemaphore(value: 0)
var code: Int32 = 0
Task {
    do {
        let duration = try await asset.load(.duration)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        print("AV_DURATION=\(CMTimeGetSeconds(duration)) VIDEO_TRACKS=\(tracks.count)")
        if tracks.isEmpty { code = 3 }
    } catch {
        print("AV_ERROR=\(error)")
        code = 4
    }
    sem.signal()
}
sem.wait()
exit(code)
