import AppKit
import CoreGraphics
import Foundation

let args = CommandLine.arguments
let output = args.count > 1 ? args[1] : "src-tauri/icons/icon.png"
let size: CGFloat = 1024
let image = NSImage(size: NSSize(width: size, height: size))

image.lockFocus()
guard let ctx = NSGraphicsContext.current?.cgContext else {
  fputs("ENDLUME icon: no graphics context\n", stderr)
  exit(2)
}
ctx.clear(CGRect(x: 0, y: 0, width: size, height: size))

func drawGradientRing(_ rect: CGRect, _ colors: [NSColor]) {
  ctx.saveGState()
  ctx.addEllipse(in: rect)
  ctx.setLineWidth(72)
  ctx.replacePathWithStrokedPath()
  ctx.clip()
  let cgColors = colors.map { $0.cgColor } as CFArray
  guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: [0, 1]) else {
    ctx.restoreGState(); return
  }
  ctx.drawLinearGradient(
    gradient,
    start: CGPoint(x: rect.minX, y: rect.midY),
    end: CGPoint(x: rect.maxX, y: rect.midY),
    options: []
  )
  ctx.restoreGState()
}

// Original ENDLUME identity: only the cyan/violet/magenta infinity mark,
// without the later black rounded-square frame.
drawGradientRing(
  CGRect(x: 170, y: 322, width: 400, height: 380),
  [NSColor(calibratedRed: 0.18, green: 0.75, blue: 1.0, alpha: 1),
   NSColor(calibratedRed: 0.48, green: 0.29, blue: 1.0, alpha: 1)]
)
drawGradientRing(
  CGRect(x: 454, y: 322, width: 400, height: 380),
  [NSColor(calibratedRed: 0.48, green: 0.29, blue: 1.0, alpha: 1),
   NSColor(calibratedRed: 1.0, green: 0.20, blue: 0.64, alpha: 1)]
)
image.unlockFocus()

guard let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
  fputs("ENDLUME icon: PNG encode failed\n", stderr)
  exit(3)
}
try png.write(to: URL(fileURLWithPath: output), options: .atomic)
print("ENDLUME original brand icon restored: \(output)")
