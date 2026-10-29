import Foundation
import PDFKit
import Vision
import CoreGraphics
import AppKit
import CoreText

enum OCRError: Error { case invalidPDF, tooLarge, noImage }

// Make a single-page image-only fixture for the live acceptance test.
if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--fixture" {
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    guard let imageContext = CGContext(data: nil, width: 1400, height: 300, bitsPerComponent: 8, bytesPerRow: 5600, space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { throw OCRError.noImage }
    imageContext.setFillColor(CGColor(gray: 1, alpha: 1))
    imageContext.fill(CGRect(x: 0, y: 0, width: 1400, height: 300))
    imageContext.textPosition = CGPoint(x: 50, y: 140)
    let text = NSAttributedString(string: "Warranty covers twelve months from purchase.", attributes: [.font: NSFont.systemFont(ofSize: 42), .foregroundColor: NSColor.black])
    CTLineDraw(CTLineCreateWithAttributedString(text), imageContext)
    guard let image = imageContext.makeImage(), let consumer = CGDataConsumer(url: URL(fileURLWithPath: CommandLine.arguments[2]) as CFURL) else { throw OCRError.noImage }
    var box = CGRect(x: 0, y: 0, width: 700, height: 150)
    guard let pdf = CGContext(consumer: consumer, mediaBox: &box, nil) else { throw OCRError.invalidPDF }
    pdf.beginPDFPage(nil)
    pdf.draw(image, in: box)
    pdf.endPDFPage()
    pdf.closePDF()
    exit(0)
}

guard CommandLine.arguments.count == 2, let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])), !document.isEncrypted, document.pageCount <= 100 else { throw OCRError.invalidPDF }
var pages: [[String: Any]] = []
var textCount = 0
for number in 0..<document.pageCount {
    let text: String = try autoreleasepool {
        guard let page = document.page(at: number) else { throw OCRError.invalidPDF }
        let bounds = page.bounds(for: .mediaBox)
        guard bounds.width > 0, bounds.height > 0 else { throw OCRError.invalidPDF }
        let scale = min(2.0, 2000.0 / max(bounds.width, bounds.height))
        let width = max(1, Int(ceil(bounds.width * scale)))
        let height = max(1, Int(ceil(bounds.height * scale)))
        guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { throw OCRError.noImage }
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.scaleBy(x: scale, y: scale)
        context.translateBy(x: -bounds.origin.x, y: -bounds.origin.y)
        page.draw(with: .mediaBox, to: context)
        guard let image = context.makeImage() else { throw OCRError.noImage }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        request.usesLanguageCorrection = true
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    }
    textCount += text.count
    guard textCount <= 200000 else { throw OCRError.tooLarge }
    pages.append(["number": number + 1, "text": text])
}
let output = try JSONSerialization.data(withJSONObject: ["pages": pages], options: [.sortedKeys])
FileHandle.standardOutput.write(output)
